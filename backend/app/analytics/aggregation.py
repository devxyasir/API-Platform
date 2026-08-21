"""Hourly usage rollups into ``UsageAggregate`` (billing-ready + fast long-range charts)."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models.enums import RequestStatus
from app.models.request_log import RequestLog
from app.models.usage import UsageAggregate
from app.utils.time import utcnow

logger = get_logger("app.analytics.aggregation")


def _hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


async def rollup_recent(session: AsyncSession, hours: int = 3) -> int:
    """Recompute hourly aggregates for the last ``hours`` hours (idempotent)."""
    since = _hour(utcnow() - timedelta(hours=hours))
    result = await session.execute(select(RequestLog).where(RequestLog.started_at >= since))
    rows = result.scalars().all()

    grouped: dict[tuple, dict] = defaultdict(
        lambda: {
            "requests": 0, "successful": 0, "failed": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "latency_sum": 0.0,
        }
    )
    for r in rows:
        key = (_hour(r.started_at), r.user_id or "", r.project_id or "", r.model or "")
        g = grouped[key]
        g["requests"] += 1
        if r.status == RequestStatus.SUCCESS:
            g["successful"] += 1
            g["latency_sum"] += r.latency_ms
        else:
            g["failed"] += 1
        g["prompt_tokens"] += r.prompt_tokens
        g["completion_tokens"] += r.completion_tokens
        g["total_tokens"] += r.total_tokens

    written = 0
    for (bucket, user_id, project_id, model), g in grouped.items():
        existing = await session.execute(
            select(UsageAggregate).where(
                and_(
                    UsageAggregate.bucket == bucket,
                    UsageAggregate.user_id == user_id,
                    UsageAggregate.project_id == project_id,
                    UsageAggregate.model == model,
                )
            )
        )
        agg = existing.scalar_one_or_none()
        if agg is None:
            agg = UsageAggregate(bucket=bucket, user_id=user_id, project_id=project_id, model=model)
            session.add(agg)
        agg.requests = g["requests"]
        agg.successful = g["successful"]
        agg.failed = g["failed"]
        agg.prompt_tokens = g["prompt_tokens"]
        agg.completion_tokens = g["completion_tokens"]
        agg.total_tokens = g["total_tokens"]
        agg.latency_sum_ms = g["latency_sum"]
        written += 1

    await session.flush()
    logger.info("usage_rollup", extra={"buckets": written, "window_hours": hours})
    return written
