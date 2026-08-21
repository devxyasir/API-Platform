"""Notrack (https://notrack.ai) upstream adapter.

Notrack is an anonymous, keyless AI debate service. It does NOT speak the OpenAI
wire format: a single ``POST /api/dispatch`` endpoint returns a server-sent event
stream. This adapter translates the normalized OpenAI-style chat request into a
dispatch body and turns the SSE events back into ``StreamChunk`` / ``ChatResult``.

Wire format (captured from the browser HAR):

    POST https://notrack.ai/api/dispatch
    {"user_input": "...", "mode": "usual", "model": "C", "persona": "normal",
     "max_turns": 6, "chat_id": null, "attachments": [],
     "regenerate": false, "edit": false, "edit_mid": null}

SSE events (one JSON object per ``data:`` line):

    {"type":"chat_meta","chat_id":"...","mode":"usual"}
    {"type":"user","turn":0,"content":"...","message_id":"..."}
    {"type":"thinking","speaker":"C","turn":1}
    {"type":"delta","speaker":"C","turn":1,"chunk":"..."}   # streamed text
    {"type":"message","speaker":"C","turn":1,"content":"..."} # full message
    {"type":"done"}

No credentials are required (the service tracks its anonymous user server-side),
so this adapter sends browser-like headers instead of an Authorization header.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.providers.base import ChatRequest, ChatResult, LLMProvider, StreamChunk
from app.providers.errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from app.utils.time import utcnow

logger = get_logger("app.providers.notrack")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# Dispatch body fields the gateway payload may override (debate knobs).
_OVERRIDABLE = ("mode", "persona", "max_turns", "chat_id", "attachments",
                "regenerate", "edit", "edit_mid")


class NotrackProvider(LLMProvider):
    name = "notrack"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    # --- helpers -------------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{settings.notrack_base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        origin = settings.notrack_base_url.rstrip("/")
        return {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Accept-Language": "en-GB,en;q=0.9",
            "Origin": origin,
            "Referer": f"{origin}/chat",
            "User-Agent": _USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    @staticmethod
    def _text_of(part: Any) -> str:
        if isinstance(part, str):
            return part
        if isinstance(part, list):
            return "".join(
                p.get("text", "") for p in part
                if isinstance(p, dict) and p.get("type") == "text"
            )
        return ""

    def _last_user_text(self, messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return self._text_of(message.get("content"))
        return ""

    def _build_body(self, request: ChatRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "user_input": self._last_user_text(request.messages),
            "mode": settings.notrack_mode,
            "model": request.model_upstream,
            "persona": settings.notrack_persona,
            "max_turns": settings.notrack_max_turns,
            "chat_id": None,
            "attachments": [],
            "regenerate": False,
            "edit": False,
            "edit_mid": None,
        }
        for key in _OVERRIDABLE:
            if key in request.payload:
                body[key] = request.payload[key]
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
            provider_request_id=resp.headers.get("cf-ray"),
        )

    # --- SSE parsing ---------------------------------------------------------
    @staticmethod
    def _parse_event_lines(text: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if not data_str:
                continue
            try:
                events.append(json.loads(data_str))
            except json.JSONDecodeError:
                logger.warning("malformed_sse_chunk")
        return events

    # --- non-streaming -------------------------------------------------------
    async def chat(self, request: ChatRequest) -> ChatResult:
        body = self._build_body(request)
        try:
            resp = await self._client.post(
                self._url("/api/dispatch"), json=body, headers=self._headers()
            )
            text = resp.text
            self._raise_for_status(resp, text)
            events = self._parse_event_lines(text)
        except (httpx.TimeoutException,) as exc:
            raise UpstreamTimeout() from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Upstream connection error: {exc}") from exc
        return self._to_result(events, request)

    def _to_result(self, events: list[dict[str, Any]], request: ChatRequest) -> ChatResult:
        deltas: list[str] = []
        full_message = ""
        chat_id = ""
        for event in events:
            etype = event.get("type")
            if etype == "chat_meta":
                chat_id = event.get("chat_id") or ""
            elif etype == "delta":
                chunk = event.get("chunk") or ""
                if chunk:
                    deltas.append(chunk)
            elif etype == "message":
                full_message = event.get("content") or ""
        content = full_message or "".join(deltas)
        return ChatResult(
            id=f"notrack-{chat_id}" if chat_id else "",
            model=request.model_public,
            created=int(utcnow().timestamp()),
            choices=[
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            usage=None,
            provider_request_id=chat_id or None,
            raw={"events": events},
        )

    # --- streaming -----------------------------------------------------------
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        body = self._build_body(request)
        try:
            async with self._client.stream(
                "POST", self._url("/api/dispatch"), json=body, headers=self._headers()
            ) as resp:
                if resp.status_code >= 400:
                    err_text = (await resp.aread()).decode("utf-8", "replace")
                    self._raise_for_status(resp, err_text)
                async for chunk in self._parse_sse(resp):
                    yield chunk
        except httpx.TimeoutException:
            raise UpstreamTimeout()
        except httpx.HTTPError as exc:
            raise UpstreamUnavailable(f"Upstream stream error: {exc}")

    async def _parse_sse(self, resp: httpx.Response) -> AsyncIterator[StreamChunk]:
        yielded_any = False
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if not data_str:
                continue
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "delta":
                chunk = event.get("chunk") or ""
                if chunk:
                    yielded_any = True
                    yield StreamChunk(delta=chunk, raw=event)
            elif etype == "message":
                # The upstream also sends the complete message; emit it as a
                # single chunk only when no deltas arrived, then close the turn.
                if not yielded_any and event.get("content"):
                    yield StreamChunk(delta=event["content"], raw=event)
                yield StreamChunk(finish_reason="stop", raw=event)
            elif etype == "done":
                yield StreamChunk(finish_reason="stop", raw=event)
                break

    # --- health --------------------------------------------------------------
    async def health_check(self) -> tuple[bool, float | None]:
        start = utcnow()
        try:
            resp = await self._client.get(self._url("/api/chats"), headers=self._headers(), timeout=10.0)
            latency = (utcnow() - start).total_seconds() * 1000
            return resp.status_code < 500, latency
        except httpx.HTTPError:
            return False, None