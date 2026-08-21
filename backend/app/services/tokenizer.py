"""Token accounting.

Prefers provider-reported usage. When the upstream does not return token counts
(e.g. some streaming responses), we fall back to a tokenizer estimate and clearly
mark it as ``tokenizer_estimated`` so the distinction is never lost.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.logging_config import get_logger
from app.models.enums import TokenCountSource

logger = get_logger("app.tokenizer")

try:  # tiktoken is optional; degrade gracefully if unavailable.
    import tiktoken

    _TIKTOKEN = True
except Exception:  # pragma: no cover
    tiktoken = None  # type: ignore
    _TIKTOKEN = False


@lru_cache(maxsize=32)
def _encoding(model: str):
    if not _TIKTOKEN:
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:  # pragma: no cover
            return None


def count_text(text: str, model: str = "gpt-4o") -> int:
    if not text:
        return 0
    enc = _encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:  # pragma: no cover
            pass
    # Heuristic fallback: ~4 chars per token.
    return max(1, len(text) // 4)


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict):
                out.append(part.get("text", "") or "")
            elif isinstance(part, str):
                out.append(part)
        return " ".join(out)
    return str(content)


def count_messages(messages: list[dict[str, Any]], model: str = "gpt-4o") -> int:
    """Estimate prompt tokens for a chat message list (OpenAI-style overhead)."""
    total = 0
    for msg in messages:
        total += 4  # per-message overhead
        total += count_text(msg.get("role", ""), model)
        total += count_text(_content_to_text(msg.get("content")), model)
        if msg.get("name"):
            total += count_text(str(msg["name"]), model)
    return total + 2  # priming


def estimate_usage(messages: list[dict[str, Any]], completion_text: str,
                   model: str = "gpt-4o") -> tuple[int, int, int, str]:
    prompt = count_messages(messages, model)
    completion = count_text(completion_text, model)
    return prompt, completion, prompt + completion, TokenCountSource.TOKENIZER_ESTIMATED
