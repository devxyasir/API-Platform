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
from pathlib import Path
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

    def _format_tools(self, payload: dict[str, Any]) -> str:
        tools = payload.get("tools") or []
        functions = payload.get("functions") or []
        if not tools and not functions:
            return ""

        tool_signatures: list[str] = []
        for t in tools:
            if isinstance(t, dict):
                fn = t.get("function", t)
                name = fn.get("name", "tool")
                desc = (fn.get("description") or "").split("\n")[0].split(". ")[0].strip()
                props = fn.get("parameters", {}).get("properties", {})
                req = set(fn.get("parameters", {}).get("required", []))
                param_strs = [
                    f"{p_name}: {p_spec.get('type', 'any')}" if p_name in req else f"{p_name}?: {p_spec.get('type', 'any')}"
                    for p_name, p_spec in props.items()
                ]
                sig = f"- `{name}({', '.join(param_strs)})`"
                if desc:
                    sig += f": {desc}"
                tool_signatures.append(sig)

        for f in functions:
            if isinstance(f, dict):
                name = f.get("name", "function")
                desc = (f.get("description") or "").split("\n")[0].split(". ")[0].strip()
                props = f.get("parameters", {}).get("properties", {})
                req = set(f.get("parameters", {}).get("required", []))
                param_strs = [
                    f"{p_name}: {p_spec.get('type', 'any')}" if p_name in req else f"{p_name}?: {p_spec.get('type', 'any')}"
                    for p_name, p_spec in props.items()
                ]
                sig = f"- `{name}({', '.join(param_strs)})`"
                if desc:
                    sig += f": {desc}"
                tool_signatures.append(sig)

        if tool_signatures:
            return "Available Tools:\n" + "\n".join(tool_signatures)
        return ""

    def _format_prompt(
        self, messages: list[dict[str, Any]], payload: dict[str, Any] | None = None
    ) -> str:
        """Combine base persona (from config), compact tool signatures,
        and conversation history into a unified prompt safely budgeted for notrack's 4000 char limit."""
        system_prompts: list[str] = []
        dialogue: list[dict[str, str]] = []

        # 1. Base system prompt from backend configuration (.env or markdown file)
        base_prompt = settings.get_notrack_system_prompt()
        if base_prompt:
            system_prompts.append(base_prompt)

        # 2. Extract caller agent's system prompts and user/assistant dialogue turns
        for msg in messages:
            role = msg.get("role", "user")
            content = self._text_of(msg.get("content"))
            if not content:
                continue
            if role == "system":
                # For very long system prompts (e.g. OpenCode CLI rules), extract key instructions
                if len(content) > 600:
                    summary_lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("<")][:6]
                    system_prompts.append("Agent Guidelines:\n" + "\n".join(summary_lines))
                else:
                    system_prompts.append(content)
            elif role in ("user", "assistant"):
                dialogue.append({"role": role, "content": content})

        # 3. Include compact tool definitions declared by the agent
        if payload:
            tools_desc = self._format_tools(payload)
            if tools_desc:
                system_prompts.append(tools_desc)

        system_instruction = "\n\n".join(system_prompts).strip()

        # If it's a simple single user message with no history:
        if len(dialogue) == 1 and dialogue[0]["role"] == "user":
            user_text = dialogue[0]["content"]
            if system_instruction:
                formatted = f"[System Instructions:\n{system_instruction}]\n\n{user_text}"
            else:
                formatted = user_text
        else:
            # Multi-turn history: Keep the most recent turns that fit budget
            recent_dialogue = dialogue[-6:] if len(dialogue) > 6 else dialogue
            dialogue_lines: list[str] = []
            for msg in recent_dialogue:
                speaker = "User" if msg["role"] == "user" else "Assistant"
                # Trim overly long assistant outputs in history
                turn_content = msg["content"]
                if len(turn_content) > 500:
                    turn_content = turn_content[:500] + "... [truncated]"
                dialogue_lines.append(f"{speaker}: {turn_content}")

            dialogue_text = "\n\n".join(dialogue_lines)
            if system_instruction:
                formatted = f"[System Instructions:\n{system_instruction}]\n\n{dialogue_text}"
            else:
                formatted = dialogue_text or (system_instruction if system_instruction else "")

        # Strict safety cap: Upstream notrack.ai enforces max 4000 chars on user_input
        max_limit = 3900
        if len(formatted) > max_limit:
            # Keep user text intact, truncate system instructions from head
            last_turn = dialogue[-1]["content"] if dialogue else ""
            avail_for_sys = max(100, max_limit - len(last_turn) - 40)
            trimmed_sys = system_instruction[:avail_for_sys].rsplit("\n", 1)[0]
            formatted = f"[System Instructions:\n{trimmed_sys}]\n\nUser: {last_turn}"
            if len(formatted) > max_limit:
                formatted = formatted[:max_limit]

        return formatted

    def _resolve_persona_and_mode(self, request: ChatRequest) -> tuple[str, str, int]:
        model_name = (request.model_public or "").lower()
        payload = request.payload or {}

        persona = payload.get("persona") or settings.notrack_persona
        mode = payload.get("mode") or settings.notrack_mode
        max_turns = payload.get("max_turns") or settings.notrack_max_turns

        if "creative" in model_name or payload.get("style") == "creative":
            persona = "creative"
        elif "detailed" in model_name or payload.get("style") == "detailed":
            persona = "detailed"
        elif "shorter" in model_name or "concise" in model_name or payload.get("style") in ("shorter", "concise"):
            persona = "concise"
        elif "high" in model_name or payload.get("reasoning_effort") == "high":
            mode = "debate"
            max_turns = max(max_turns, 8)

        if persona == "shorter":
            persona = "concise"

        return persona, mode, max_turns

    def _build_body(self, request: ChatRequest) -> dict[str, Any]:
        persona, mode, max_turns = self._resolve_persona_and_mode(request)
        body: dict[str, Any] = {
            "user_input": self._format_prompt(request.messages, request.payload),
            "mode": mode,
            "model": request.model_upstream or "C",
            "persona": persona,
            "max_turns": max_turns,
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
            message = err.get("message") or err.get("content") or message
            code = err.get("code") or err.get("type")
        except (json.JSONDecodeError, AttributeError):
            events = self._parse_event_lines(body_text)
            for ev in events:
                if ev.get("type") == "error":
                    message = ev.get("content") or ev.get("message") or message
                    code = "upstream_error"
                    break

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

    def _save_debug_trace(
        self,
        request: ChatRequest,
        outgoing_body: dict[str, Any],
        status_code: int | None = None,
        response_text: str | None = None,
        error: str | None = None,
    ) -> None:
        try:
            debug_data = {
                "timestamp": utcnow().isoformat(),
                "incoming_from_client": {
                    "model_requested": request.model_public,
                    "model_upstream": request.model_upstream,
                    "stream": request.stream,
                    "messages_count": len(request.messages),
                    "messages": request.messages,
                    "tools": request.payload.get("tools"),
                    "raw_payload": request.payload,
                },
                "outgoing_to_notrack": {
                    "url": self._url("/api/dispatch"),
                    "headers": self._headers(),
                    "body": outgoing_body,
                    "user_input_length": len(outgoing_body.get("user_input", "")),
                },
                "upstream_response": {
                    "status_code": status_code,
                    "response_preview": response_text[:2000] if response_text else None,
                    "error": error,
                },
            }
            debug_file = Path(__file__).resolve().parent.parent.parent / "debug_notrack_request.json"
            debug_file.write_text(json.dumps(debug_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("failed_to_save_debug_trace", extra={"error": str(e)})

    # --- non-streaming -------------------------------------------------------
    async def chat(self, request: ChatRequest) -> ChatResult:
        body = self._build_body(request)
        try:
            resp = await self._client.post(
                self._url("/api/dispatch"), json=body, headers=self._headers()
            )
            text = resp.text
            self._save_debug_trace(request, body, status_code=resp.status_code, response_text=text)
            self._raise_for_status(resp, text)
            events = self._parse_event_lines(text)
        except (httpx.TimeoutException,) as exc:
            self._save_debug_trace(request, body, error=f"Timeout: {exc}")
            raise UpstreamTimeout() from exc
        except httpx.HTTPError as exc:
            self._save_debug_trace(request, body, error=f"HTTPError: {exc}")
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
            elif etype == "error":
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
                    self._save_debug_trace(request, body, status_code=resp.status_code, response_text=err_text)
                    self._raise_for_status(resp, err_text)
                else:
                    self._save_debug_trace(request, body, status_code=resp.status_code, response_text="[Stream Started 200 OK]")
                async for chunk in self._parse_sse(resp):
                    yield chunk
        except httpx.TimeoutException:
            self._save_debug_trace(request, body, error="Stream Timeout")
            raise UpstreamTimeout()
        except httpx.HTTPError as exc:
            self._save_debug_trace(request, body, error=f"Stream HTTPError: {exc}")
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