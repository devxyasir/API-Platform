"""Usage analytics computed from the request log.

For local/personal volumes we aggregate directly over the indexed ``requests``
table (flexible filtering, exact numbers). ``UsageAggregate`` rollups exist for
scaling long time ranges — see ``analytics.aggregation``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.enums import RequestStatus
from app.models.request_log import RequestLog
from app.models.user import User
from app.utils.time import utcnow


@dataclass
class Filters:
    since: datetime
    until: datetime
    user_id: str | None = None
    project_id: str | None = None
    api_key_id: str | None = None
    model: str | None = None
    endpoint: str | None = None
    status: str | None = None


def _apply(stmt, f: Filters):
    stmt = stmt.where(RequestLog.started_at >= f.since, RequestLog.started_at <= f.until)
    if f.user_id:
        stmt = stmt.where(RequestLog.user_id == f.user_id)
    if f.project_id:
        stmt = stmt.where(RequestLog.project_id == f.project_id)
    if f.api_key_id:
        stmt = stmt.where(RequestLog.api_key_id == f.api_key_id)
    if f.model:
        stmt = stmt.where(RequestLog.model == f.model)
    if f.endpoint:
        stmt = stmt.where(RequestLog.endpoint == f.endpoint)
    if f.status:
        stmt = stmt.where(RequestLog.status == f.status)
    return stmt


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac, 2)


async def _fetch_rows(session: AsyncSession, f: Filters) -> list[tuple]:
    stmt = _apply(
        select(
            RequestLog.started_at,
            RequestLog.status,
            RequestLog.status_code,
            RequestLog.total_tokens,
            RequestLog.prompt_tokens,
            RequestLog.completion_tokens,
            RequestLog.latency_ms,
            RequestLog.model,
            RequestLog.endpoint,
            RequestLog.user_id,
        ),
        f,
    ).order_by(RequestLog.started_at)
    result = await session.execute(stmt)
    return list(result.all())


async def overview(session: AsyncSession, f: Filters) -> dict:
    rows = await _fetch_rows(session, f)
    total = len(rows)
    successful = sum(1 for r in rows if r.status == RequestStatus.SUCCESS)
    failed = sum(1 for r in rows if r.status in (RequestStatus.ERROR, RequestStatus.TIMEOUT))
    rate_limited = sum(1 for r in rows if r.status == RequestStatus.RATE_LIMITED)
    provider_errors = sum(1 for r in rows if r.status_code in (502, 503, 504))
    prompt_tokens = sum(r.prompt_tokens for r in rows)
    completion_tokens = sum(r.completion_tokens for r in rows)
    total_tokens = sum(r.total_tokens for r in rows)
    latencies = sorted(r.latency_ms for r in rows if r.status == RequestStatus.SUCCESS)

    return {
        "total_requests": total,
        "successful_requests": successful,
        "failed_requests": failed,
        "rate_limited_requests": rate_limited,
        "provider_errors": provider_errors,
        "error_rate": round((failed + rate_limited) / total, 4) if total else 0.0,
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "p99_latency_ms": _percentile(latencies, 0.99),
    }


async def timeseries(session: AsyncSession, f: Filters, bucket: str = "hour") -> list[dict]:
    rows = await _fetch_rows(session, f)
    span = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)

    def trunc(dt: datetime) -> datetime:
        if bucket == "hour":
            return dt.replace(minute=0, second=0, microsecond=0)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    buckets: dict[datetime, dict] = defaultdict(
        lambda: {"requests": 0, "errors": 0, "tokens": 0, "latency_sum": 0.0, "latency_n": 0}
    )
    for r in rows:
        b = trunc(r.started_at)
        agg = buckets[b]
        agg["requests"] += 1
        if r.status != RequestStatus.SUCCESS:
            agg["errors"] += 1
        agg["tokens"] += r.total_tokens
        if r.status == RequestStatus.SUCCESS:
            agg["latency_sum"] += r.latency_ms
            agg["latency_n"] += 1

    # Fill empty buckets across the range for smooth charts.
    points: list[dict] = []
    cursor = trunc(f.since)
    end = trunc(f.until)
    while cursor <= end:
        agg = buckets.get(cursor)
        points.append(
            {
                "ts": cursor.isoformat(),
                "requests": agg["requests"] if agg else 0,
                "errors": agg["errors"] if agg else 0,
                "tokens": agg["tokens"] if agg else 0,
                "avg_latency_ms": round(agg["latency_sum"] / agg["latency_n"], 2)
                if agg and agg["latency_n"]
                else 0.0,
            }
        )
        cursor += span
    return points


async def breakdown(session: AsyncSession, f: Filters, field_name: str) -> list[dict]:
    rows = await _fetch_rows(session, f)
    counts: dict[str, dict] = defaultdict(lambda: {"requests": 0, "tokens": 0})
    for r in rows:
        key = getattr(r, field_name) or "unknown"
        counts[key]["requests"] += 1
        counts[key]["tokens"] += r.total_tokens
    out = [{"key": k, **v} for k, v in counts.items()]
    out.sort(key=lambda x: x["requests"], reverse=True)
    return out


async def active_counts(session: AsyncSession, since: datetime) -> dict:
    active_users = await session.execute(
        select(func.count(func.distinct(RequestLog.user_id))).where(RequestLog.started_at >= since)
    )
    active_keys = await session.execute(
        select(func.count(func.distinct(RequestLog.api_key_id))).where(RequestLog.started_at >= since)
    )
    total_users = await session.execute(select(func.count()).select_from(User))
    total_keys = await session.execute(select(func.count()).select_from(ApiKey))
    return {
        "active_users": int(active_users.scalar() or 0),
        "active_api_keys": int(active_keys.scalar() or 0),
        "total_users": int(total_users.scalar() or 0),
        "total_api_keys": int(total_keys.scalar() or 0),
    }


async def user_stats(session: AsyncSession, user_id: str, days: int = 30) -> dict:
    f = Filters(since=utcnow() - timedelta(days=days), until=utcnow(), user_id=user_id)
    ov = await overview(session, f)
    top_models = await breakdown(session, f, "model")
    top_endpoints = await breakdown(session, f, "endpoint")
    last = await session.execute(
        select(func.max(RequestLog.started_at)).where(RequestLog.user_id == user_id)
    )
    last_active = last.scalar()
    return {
        **ov,
        "top_models": top_models[:5],
        "top_endpoints": top_endpoints[:5],
        "last_active": last_active.isoformat() if last_active else None,
    }
