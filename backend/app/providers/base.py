"""Provider-agnostic LLM interface.

The public API layer speaks in these normalized types; concrete adapters
(``openai_provider``, future ``anthropic``, ``google`` …) translate to/from the
upstream wire format. Upstream credentials NEVER leave the adapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import TokenCountSource


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    source: str = TokenCountSource.PROVIDER_REPORTED

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(slots=True)
class ChatRequest:
    """A normalized chat request.

    ``payload`` is an OpenAI-style body (the internal lingua franca). Adapters may
    read individual fields or forward the whole payload. ``model_upstream`` is the
    id the adapter should actually send upstream.
    """

    model_public: str
    model_upstream: str
    payload: dict[str, Any]
    stream: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self.payload.get("messages", [])


@dataclass(slots=True)
class ChatResult:
    id: str
    model: str
    created: int
    choices: list[dict[str, Any]]  # OpenAI-style choice objects (passed through)
    usage: Usage | None = None
    provider_request_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Concatenated assistant text across choices (for logging / Anthropic map)."""
        parts: list[str] = []
        for ch in self.choices:
            msg = ch.get("message", {})
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(p.get("text", "") for p in content if isinstance(p, dict))
        return "".join(parts)


@dataclass(slots=True)
class StreamChunk:
    delta: str = ""
    role: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    raw: dict[str, Any] | None = None
    # Raw upstream ``choices`` array for this SSE event, passed through verbatim so
    # tool_calls / function_call / refusal / logprobs and n>1 choices survive. When
    # set, the API layer forwards these instead of reconstructing role+content.
    choices: list[dict[str, Any]] | None = None


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResult:
        ...

    @abstractmethod
    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        ...

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        """Return one embedding vector per input text.

        Optional capability: only providers that expose an embeddings endpoint override
        this. The default refuses so a provider without embeddings (e.g. notrack) never
        silently returns garbage — callers treat the failure as "recall unavailable" and
        continue without it. Credentials never leave the adapter (same rule as ``chat``)."""
        raise NotImplementedError(f"Provider '{self.name}' does not support embeddings.")

    async def health_check(self) -> tuple[bool, float | None]:
        """Return (ok, latency_ms)."""
        return True, None
