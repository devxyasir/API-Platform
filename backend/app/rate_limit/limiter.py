"""Rate-limit enforcement: fixed-window request/token limits + standard headers."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.rate_limit.backends import RateBackend

WINDOWS = {"rpm": 60, "rph": 3600, "rpd": 86400, "tpm": 60, "tpd": 86400}


@dataclass(slots=True)
class LimitSet:
    rpm: int | None = None
    rph: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None
    concurrency: int | None = None


@dataclass(slots=True)
class Decision:
    allowed: bool
    headers: dict[str, str] = field(default_factory=dict)
    limit_type: str | None = None
    limit_value: int = 0
    retry_after: int = 0


class RateLimiter:
    def __init__(self, backend: RateBackend) -> None:
        self.backend = backend

    async def check_request(self, scope_id: str, limits: LimitSet) -> Decision:
        now = time.time()
        headers: dict[str, str] = {}

        # --- request-count windows (increment atomically, then compare) ---
        for name in ("rpm", "rph", "rpd"):
            limit = getattr(limits, name)
            if limit is None:
                continue
            window = WINDOWS[name]
            bucket = int(now // window)
            key = f"rl:{scope_id}:{name}:{bucket}"
            count = await self.backend.incr(key, ttl=window * 2, amount=1)
            reset = int((bucket + 1) * window)
            if name == "rpm":
                headers = {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(max(0, limit - count)),
                    "X-RateLimit-Reset": str(reset),
                }
            if count > limit:
                retry = max(1, reset - int(now))
                headers["Retry-After"] = str(retry)
                return Decision(False, headers, name, limit, retry)

        # --- token windows (peek only; tokens are added post-response) ---
        for name in ("tpm", "tpd"):
            limit = getattr(limits, name)
            if limit is None:
                continue
            window = WINDOWS[name]
            bucket = int(now // window)
            key = f"rl:{scope_id}:{name}:{bucket}"
            count = await self.backend.get_int(key)
            if count >= limit:
                reset = int((bucket + 1) * window)
                retry = max(1, reset - int(now))
                headers["Retry-After"] = str(retry)
                return Decision(False, headers, name, limit, retry)

        return Decision(True, headers)

    async def add_tokens(self, scope_id: str, tokens: int, limits: LimitSet) -> None:
        if tokens <= 0:
            return
        now = time.time()
        for name in ("tpm", "tpd"):
            if getattr(limits, name) is None:
                continue
            window = WINDOWS[name]
            bucket = int(now // window)
            key = f"rl:{scope_id}:{name}:{bucket}"
            await self.backend.incr(key, ttl=window * 2, amount=tokens)
