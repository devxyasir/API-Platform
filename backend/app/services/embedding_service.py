"""Embeddings + similarity helpers for long-term memory and semantic recall.

Thin, best-effort layer over the provider's ``embed`` capability:

* Embeddings always go through the OpenAI provider on the deployment owner's own account
  (never ``notrack`` — that adapter has no embeddings and must not be used here).
* Every call is best-effort: if embeddings are disabled or the upstream is unavailable,
  the helpers return ``None``/empty and the caller silently continues without recall.
  Chat must never fail because embeddings are down.
* Similarity is a pure-Python cosine over JSON vectors. At personal scale (one user's
  rows) an O(N) scan is sub-millisecond and avoids a native vector-extension dependency.
"""
from __future__ import annotations

import math

from app.config import settings
from app.logging_config import get_logger
from app.providers import registry

logger = get_logger("app.services.embedding")


async def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of texts. Returns one vector per input, or ``None`` if embeddings
    are disabled or the upstream call fails (best-effort — never raises)."""
    if not settings.embeddings_enabled or not texts:
        return None
    # Always the OpenAI provider — notrack has no embeddings and is out of scope here.
    provider = registry.get("openai")
    try:
        vectors = await provider.embed(texts, model=settings.embedding_model)
    except Exception:  # NotImplementedError, upstream errors, timeouts — all non-fatal.
        logger.warning("embed_failed", extra={"count": len(texts)})
        return None
    if not vectors or len(vectors) != len(texts):
        return None
    return vectors


async def embed_one(text: str) -> list[float] | None:
    """Embed a single string, or ``None`` on any failure."""
    text = (text or "").strip()
    if not text:
        return None
    vectors = await embed_texts([text])
    return vectors[0] if vectors else None


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors. Returns 0.0 for empty/degenerate
    inputs (so a missing embedding simply ranks last rather than raising)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def top_k(
    query: list[float] | None,
    candidates: list[tuple[object, list[float] | None]],
    k: int,
    *,
    min_score: float = 0.0,
) -> list[tuple[object, float]]:
    """Rank ``(item, vector)`` candidates by cosine similarity to ``query`` and return the
    top ``k`` as ``(item, score)``. Empty query, empty candidates or ``k <= 0`` yield ``[]``.
    Candidates scoring at or below ``min_score`` are dropped so weak matches never pad the
    context of a low-budget model with noise."""
    if not query or k <= 0 or not candidates:
        return []
    scored: list[tuple[object, float]] = []
    for item, vec in candidates:
        score = cosine(query, vec or [])
        if score > min_score:
            scored.append((item, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
