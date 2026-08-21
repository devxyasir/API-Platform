"""OpenAI (and OpenAI-compatible) upstream adapter.

This is the ONLY component that knows how to talk to the upstream. It reads the
authorized credentials from configuration and never exposes them to callers.
"""
from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.providers.base import ChatRequest, ChatResult, LLMProvider, StreamChunk, Usage
from app.providers.errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from app.utils.time import utcnow

logger = get_logger("app.providers.openai")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    # --- helpers -------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        mode = settings.upstream_auth_mode
        key = settings.upstream_api_key
        if mode == "bearer" and key:
            headers["Authorization"] = f"Bearer {key}"
        elif mode == "header" and key:
            headers[settings.upstream_auth_header] = key
        return headers

    def _url(self, path: str) -> str:
        return f"{settings.upstream_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _build_body(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        body = dict(request.payload)
        body["model"] = request.model_upstream
        body["stream"] = stream
        if stream:
            # Ask the upstream to report token usage in the final SSE chunk.
            body["stream_options"] = {"include_usage": True}
        return body

    def _raise_for_status(self, resp: httpx.Response, body_text: str) -> None:
        if resp.status_code < 400:
            return
        message = f"Upstream returned {resp.status_code}"
        code = None
        try:
            data = json.loads(body_text)
            err = data.get("error", data)
            message = err.get("message", message)
            code = err.get("code") or err.get("type")
        except (json.JSONDecodeError, AttributeError):
            pass
        retryable = resp.status_code in (429, 500, 502, 503, 504)
        raise UpstreamError(
            message,
            status_code=resp.status_code,
            code=code,
            retryable=retryable,
            provider_request_id=resp.headers.get("x-request-id"),
        )

    # --- non-streaming -------------------------------------------------------
    async def chat(self, request: ChatRequest) -> ChatResult:
        body = self._build_body(request, stream=False)
        last_exc: Exception | None = None
        attempts = settings.upstream_max_retries + 1
        for attempt in range(attempts):
            try:
                resp = await self._client.post(
                    self._url("/chat/completions"), json=body, headers=self._headers()
                )
                text = resp.text
                self._raise_for_status(resp, text)
                data = json.loads(text)
                return self._to_result(data, request, resp.headers.get("x-request-id"))
            except (httpx.TimeoutException,) as exc:
                last_exc = UpstreamTimeout()
                logger.warning("upstream_timeout", extra={"attempt": attempt})
            except httpx.HTTPError as exc:
                last_exc = UpstreamUnavailable(f"Upstream connection error: {exc}")
                logger.warning("upstream_conn_error", extra={"attempt": attempt, "error": str(exc)})
            except UpstreamError as exc:
                if not exc.retryable or attempt == attempts - 1:
                    raise
                last_exc = exc
            await asyncio.sleep(min(2**attempt * 0.5 + random.random() * 0.2, 8))
        assert last_exc is not None
        raise last_exc

    def _to_result(self, data: dict[str, Any], request: ChatRequest, req_id: str | None) -> ChatResult:
        usage_raw = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
            total_tokens=int(usage_raw.get("total_tokens", 0)),
        ) if usage_raw else None
        return ChatResult(
            id=data.get("id", ""),
            model=request.model_public,
            created=int(data.get("created", utcnow().timestamp())),
            choices=data.get("choices", []),
            usage=usage,
            provider_request_id=data.get("id") or req_id,
            raw=data,
        )

    # --- embeddings ----------------------------------------------------------
    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """POST ``/embeddings`` and return one vector per input, ordered by index.

        Reuses the same auth headers, base URL and retry/backoff policy as ``chat`` so the
        upstream credential still never leaves this adapter. Raises the same normalized
        :class:`UpstreamError`/timeout family on failure (callers treat any embedding failure
        as "recall unavailable" and proceed without it)."""
        if not texts:
            return []
        body = {"model": model, "input": texts}
        last_exc: Exception | None = None
        attempts = settings.upstream_max_retries + 1
        for attempt in range(attempts):
            try:
                resp = await self._client.post(
                    self._url("/embeddings"), json=body, headers=self._headers()
                )
                text = resp.text
                self._raise_for_status(resp, text)
                data = json.loads(text)
                rows = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
                return [list(d.get("embedding", [])) for d in rows]
            except (httpx.TimeoutException,):
                last_exc = UpstreamTimeout()
                logger.warning("embed_upstream_timeout", extra={"attempt": attempt})
            except httpx.HTTPError as exc:
                last_exc = UpstreamUnavailable(f"Upstream connection error: {exc}")
                logger.warning("embed_upstream_conn_error", extra={"attempt": attempt, "error": str(exc)})
            except UpstreamError as exc:
                if not exc.retryable or attempt == attempts - 1:
                    raise
                last_exc = exc
            await asyncio.sleep(min(2**attempt * 0.5 + random.random() * 0.2, 8))
        assert last_exc is not None
        raise last_exc

    # --- streaming -----------------------------------------------------------
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        body = self._build_body(request, stream=True)
        try:
            async with self._client.stream(
                "POST", self._url("/chat/completions"), json=body, headers=self._headers()
            ) as resp:
                if resp.status_code >= 400:
                    err_text = (await resp.aread()).decode("utf-8", "replace")
                    self._raise_for_status(resp, err_text)
                async for chunk in self._parse_sse(resp, request):
                    yield chunk
        except httpx.TimeoutException:
            raise UpstreamTimeout()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Upstream stream error: {exc}")

    async def _parse_sse(self, resp: httpx.Response, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning("malformed_sse_chunk")
                continue

            usage = None
            if data.get("usage"):
                u = data["usage"]
                usage = Usage(
                    prompt_tokens=int(u.get("prompt_tokens", 0)),
                    completion_tokens=int(u.get("completion_tokens", 0)),
                    total_tokens=int(u.get("total_tokens", 0)),
                )

            choices = data.get("choices") or []
            if not choices:
                # Usage-only final chunk (when include_usage is set).
                if usage:
                    yield StreamChunk(usage=usage, raw=data)
                continue

            delta = choices[0].get("delta", {})
            yield StreamChunk(
                delta=delta.get("content") or "",
                role=delta.get("role"),
                finish_reason=choices[0].get("finish_reason"),
                usage=usage,
                raw=data,
                # Forward the upstream choices verbatim so tool_calls, function_call,
                # refusal, logprobs and any n>1 choices reach the client unchanged.
                choices=choices,
            )

    # --- health --------------------------------------------------------------
    async def health_check(self) -> tuple[bool, float | None]:
        start = utcnow()
        try:
            resp = await self._client.get(self._url("/models"), headers=self._headers(), timeout=10.0)
            latency = (utcnow() - start).total_seconds() * 1000
            return resp.status_code < 500, latency
        except httpx.HTTPError:
            return False, None
