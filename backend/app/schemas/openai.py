"""OpenAI-compatible request/response schemas.

The request model is intentionally permissive (``extra="allow"``) so that any
OpenAI parameter we don't explicitly model is still forwarded upstream. This
keeps the gateway compatible with new SDK features without code changes.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: Any = None  # str | list[content parts] | None (tool calls)
    name: str | None = None


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    include_usage: bool | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(..., description="Model id or alias, e.g. 'gpt-4o' or 'fast'.")
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    n: int | None = Field(default=None, ge=1, le=128)
    max_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    stop: str | list[str] | None = None
    stream: bool = False
    stream_options: StreamOptions | None = None
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    seed: int | None = None
    user: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    response_format: dict[str, Any] | None = None

    def to_upstream_payload(self) -> dict[str, Any]:
        """Serialize to an OpenAI body, dropping None values and gateway-only keys."""
        data = self.model_dump(exclude_none=True)
        data.pop("stream", None)  # managed by the provider adapter
        data.pop("stream_options", None)
        return data


# --- Response models (for documentation; the route returns pass-through dicts) ---
class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ResponseMessage(BaseModel):
    role: str
    content: str | None = None


class Choice(BaseModel):
    index: int
    message: ResponseMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class ModelObject(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "llm-gateway"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelObject]
