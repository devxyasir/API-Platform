"""Concurrency control: per-key, per-user and global in-flight request caps."""
from __future__ import annotations

from contextlib import asynccontextmanager

from app.errors import RateLimitError
from app.rate_limit.backends import RateBackend

# Safety TTL so a crashed worker can't leak concurrency slots forever.
_SLOT_TTL = 300


class ConcurrencyGuard:
    def __init__(self, backend: RateBackend) -> None:
        self.backend = backend

    @asynccontextmanager
    async def guard(self, *, key_scope: str, key_limit: int | None,
                    user_scope: str, user_limit: int | None,
                    global_limit: int | None):
        """Acquire all applicable concurrency slots; release them on exit.

        Slots are acquired most-specific first and released in reverse. If any
        acquisition fails, previously-acquired slots are released and a
        ``RateLimitError`` is raised.
        """
        acquired: list[str] = []
        checks = [
            (f"conc:global", global_limit),
            (f"conc:user:{user_scope}", user_limit),
            (f"conc:key:{key_scope}", key_limit),
        ]
        try:
            for redis_key, limit in checks:
                if limit is None:
                    continue
                ok, _current = await self.backend.acquire_concurrency(redis_key, limit, _SLOT_TTL)
                if not ok:
                    raise RateLimitError(
                        "Too many concurrent requests.",
                        code="concurrency_limit_exceeded",
                        headers={"Retry-After": "1"},
                    )
                acquired.append(redis_key)
            yield
        finally:
            for redis_key in reversed(acquired):
                await self.backend.release_concurrency(redis_key)
