"""Health & readiness probes.

- ``/health/live``  — liveness: the process is up (no external checks).
- ``/health/ready`` — readiness: dependencies (DB, cache) are reachable.
- ``/health``       — human-friendly aggregate snapshot.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import ping as db_ping
from app.providers import registry
from app.rate_limit import backend as rate_backend
from app.utils.time import utcnow

router = APIRouter(tags=["Health"])


@router.get("/health/live", summary="Liveness probe")
async def live():
    return {"status": "alive", "time": utcnow().isoformat()}


async def _cache_ok() -> bool:
    if not settings.use_redis:
        return True  # In-memory backend is always available.
    try:
        await rate_backend.get_int("healthcheck:ping")
        return True
    except Exception:
        return False


@router.get("/health/ready", summary="Readiness probe")
async def ready():
    db_ok = await db_ping()
    cache_ok = await _cache_ok()
    ready = db_ok and cache_ok
    body = {
        "status": "ready" if ready else "not_ready",
        "checks": {"database": db_ok, "cache": cache_ok},
    }
    return JSONResponse(body, status_code=200 if ready else 503)


@router.get("/health", summary="Aggregate health snapshot")
async def health():
    db_ok = await db_ping()
    breaker = registry.breaker("openai")
    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.app_name,
        "env": settings.app_env,
        "time": utcnow().isoformat(),
        "database": "up" if db_ok else "down",
        "cache": "redis" if settings.use_redis else "memory",
        "upstream_circuit": breaker.state,
    }
