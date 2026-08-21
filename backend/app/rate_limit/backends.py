"""Rate-limit storage backends.

Two implementations behind one interface:
- ``RedisBackend``  — atomic counters via INCR/EXPIRE + a Lua script for
  concurrency (safe across processes/workers).
- ``MemoryBackend`` — in-process dict guarded by a lock (perfect for local
  single-process dev; no Redis required).
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

from app.config import settings
from app.logging_config import get_logger

logger = get_logger("app.rate_limit.backend")


class RateBackend(ABC):
    @abstractmethod
    async def incr(self, key: str, ttl: int, amount: int = 1) -> int: ...

    @abstractmethod
    async def get_int(self, key: str) -> int: ...

    @abstractmethod
    async def acquire_concurrency(self, key: str, limit: int, ttl: int) -> tuple[bool, int]: ...

    @abstractmethod
    async def release_concurrency(self, key: str) -> None: ...

    @abstractmethod
    async def set_str(self, key: str, value: str, ttl: int) -> None: ...

    @abstractmethod
    async def get_str(self, key: str) -> str | None: ...

    async def close(self) -> None:  # pragma: no cover - optional
        pass


class MemoryBackend(RateBackend):
    def __init__(self) -> None:
        self._counters: dict[str, tuple[float, float]] = {}  # key -> (value, expires_at)
        self._concurrency: dict[str, int] = {}
        self._strings: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    def _expired(self, expires_at: float) -> bool:
        return expires_at != 0 and time.time() > expires_at

    async def incr(self, key: str, ttl: int, amount: int = 1) -> int:
        async with self._lock:
            value, expires = self._counters.get(key, (0.0, 0.0))
            if self._expired(expires):
                value = 0.0
            value += amount
            self._counters[key] = (value, time.time() + ttl)
            return int(value)

    async def get_int(self, key: str) -> int:
        async with self._lock:
            value, expires = self._counters.get(key, (0.0, 0.0))
            if self._expired(expires):
                return 0
            return int(value)

    async def acquire_concurrency(self, key: str, limit: int, ttl: int) -> tuple[bool, int]:
        async with self._lock:
            current = self._concurrency.get(key, 0)
            if current + 1 > limit:
                return False, current
            self._concurrency[key] = current + 1
            return True, current + 1

    async def release_concurrency(self, key: str) -> None:
        async with self._lock:
            current = self._concurrency.get(key, 0)
            self._concurrency[key] = max(0, current - 1)

    async def set_str(self, key: str, value: str, ttl: int) -> None:
        async with self._lock:
            self._strings[key] = (value, time.time() + ttl)

    async def get_str(self, key: str) -> str | None:
        async with self._lock:
            value, expires = self._strings.get(key, (None, 0.0))
            if value is None or self._expired(expires):
                return None
            return value


_ACQUIRE_LUA = """
local current = tonumber(redis.call('get', KEYS[1]) or '0')
if current + 1 > tonumber(ARGV[1]) then
  return {0, current}
end
redis.call('incr', KEYS[1])
redis.call('expire', KEYS[1], tonumber(ARGV[2]))
return {1, current + 1}
"""

_RELEASE_LUA = """
local current = tonumber(redis.call('get', KEYS[1]) or '0')
if current <= 1 then
  redis.call('del', KEYS[1])
  return 0
end
return redis.call('decr', KEYS[1])
"""


class RedisBackend(RateBackend):
    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        self._acquire = self._redis.register_script(_ACQUIRE_LUA)
        self._release = self._redis.register_script(_RELEASE_LUA)

    async def incr(self, key: str, ttl: int, amount: int = 1) -> int:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incrby(key, amount)
            pipe.expire(key, ttl)
            result = await pipe.execute()
        return int(result[0])

    async def get_int(self, key: str) -> int:
        value = await self._redis.get(key)
        return int(value) if value else 0

    async def acquire_concurrency(self, key: str, limit: int, ttl: int) -> tuple[bool, int]:
        ok, current = await self._acquire(keys=[key], args=[limit, ttl])
        return bool(ok), int(current)

    async def release_concurrency(self, key: str) -> None:
        await self._release(keys=[key])

    async def set_str(self, key: str, value: str, ttl: int) -> None:
        await self._redis.set(key, value, ex=ttl)

    async def get_str(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def close(self) -> None:
        await self._redis.aclose()


def build_backend() -> RateBackend:
    if settings.use_redis:
        try:
            backend = RedisBackend(settings.redis_url)
            logger.info("rate_limit_backend", extra={"backend": "redis"})
            return backend
        except Exception as exc:  # pragma: no cover - fall back gracefully
            logger.error("redis_init_failed", extra={"error": str(exc)})
    logger.info("rate_limit_backend", extra={"backend": "memory"})
    return MemoryBackend()
