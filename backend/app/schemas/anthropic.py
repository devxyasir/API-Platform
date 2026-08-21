"""Anthropic Messages API-compatible schemas + mapping to the internal format.

Both the OpenAI and Anthropic public endpoints funnel through the SAME provider
abstraction (an OpenAI-style payload). These helpers translate between the
Anthropic wire format and that internal representation.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.providers.base import ChatResult


class AnthropicMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: Any  # str | list[block]


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    max_tokens: int = Field(..., ge=1)
    messages: list[AnthropicMessage] = Field(..., min_length=1)
    system: Any = None  # str | list[block] | None
    temperature: float | None = Field(default=None, ge=0, le=1)
    top_p: float | None = None
    top_k: int | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    metadata: dict[str, Any] | None = None


def _blocks_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def anthropic_to_openai_payload(req: AnthropicMessagesRequest) -> dict[str, Any]:
    """Build an internal OpenAI-style payload from an Anthropic request."""
    messages: list[dict[str, Any]] = []
    system_text = _blocks_to_text(req.system)
    if system_text:
        messages.append({"role": "system", "content": system_text})
    for m in req.messages:
        messages.append({"role": m.role, "content": _blocks_to_text(m.content)})

    payload: dict[str, Any] = {"messages": messages, "max_tokens": req.max_tokens}
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.top_p is not None:
        payload["top_p"] = req.top_p
    if req.stop_sequences:
        payload["stop"] = req.stop_sequences
    return payload


_STOP_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "content_filter": "stop_sequence",
    "tool_calls": "tool_use",
    None: "end_turn",
}


def openai_finish_to_anthropic(reason: str | None) -> str:
    return _STOP_MAP.get(reason, "end_turn")


def result_to_anthropic(result: ChatResult) -> dict[str, Any]:
    text = result.text
    finish = None
    if result.choices:
        finish = result.choices[0].get("finish_reason")
    usage = result.usage
    return {
        "id": result.provider_request_id or result.id or "msg_unknown",
        "type": "message",
        "role": "assistant",
        "model": result.model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": openai_finish_to_anthropic(finish),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        },
    }
