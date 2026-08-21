"""Lightweight asyncio background scheduler.

Runs periodic jobs off the request path: provider health checks, usage rollups
and log retention cleanup. For a single-process local deployment this is plenty;
swap for Celery/RQ if you outgrow it.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import delete, select

from app.analytics.aggregation import rollup_recent
from app.database import SessionLocal
from app.logging_config import get_logger
from app.models.provider_config import ProviderConfig
from app.models.rate_limit import RateLimitEvent
from app.models.request_log import RequestLog
from app.providers import registry
from app.utils.time import utcnow

logger = get_logger("app.workers")

# Retention: keep raw request logs this many days (aggregates persist).
LOG_RETENTION_DAYS = 90


class Scheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    def start(self) -> None:
        self._stop.clear()
        self._tasks = [
            asyncio.create_task(self._loop(self.health_check, 60, "health")),
            asyncio.create_task(self._loop(self.rollup, 300, "rollup")),
            asyncio.create_task(self._loop(self.cleanup, 3600, "cleanup")),
        ]
        logger.info("scheduler_started", extra={"jobs": len(self._tasks)})

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []

    async def _loop(self, fn, interval: int, name: str) -> None:
        # Small initial delay so startup isn't slowed by background work.
        try:
            await asyncio.sleep(5)
            while not self._stop.is_set():
                try:
                    await fn()
                except Exception:
                    logger.exception("worker_job_failed", extra={"job": name})
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass

    # --- jobs ----------------------------------------------------------------
    async def health_check(self) -> None:
        provider = registry.get("openai")
        ok, latency = await provider.health_check()
        async with SessionLocal() as session:
            result = await session.execute(
                select(ProviderConfig).where(ProviderConfig.name == "openai")
            )
            cfg = result.scalar_one_or_none()
            if cfg is not None:
                cfg.last_status = "connected" if ok else "degraded"
                cfg.last_latency_ms = latency
                cfg.last_checked_at = utcnow()
                await session.commit()

    async def rollup(self) -> None:
        async with SessionLocal() as session:
            await rollup_recent(session, hours=3)
            await session.commit()

    async def cleanup(self) -> None:
        cutoff = utcnow() - timedelta(days=LOG_RETENTION_DAYS)
        async with SessionLocal() as session:
            await session.execute(delete(RequestLog).where(RequestLog.started_at < cutoff))
            await session.execute(delete(RateLimitEvent).where(RateLimitEvent.ts < cutoff))
            await session.commit()


scheduler = Scheduler()
