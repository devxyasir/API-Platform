"""Risk / abuse detection (§38).

Periodic sweeps (run by the maintenance scheduler) inspect real activity — API-key
creation bursts, repeated failed logins, token-usage spikes — and append
:class:`RiskEvent` rows for human review. Sweeps are idempotent within their window:
a detector will not open a second event for the same subject while an earlier open
event of the same type is still within the look-back window."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models.api_key import ApiKey
from app.models.enums import RiskEventType, RiskStatus, SecurityEventType, Severity
from app.models.security import RiskEvent, SecurityEvent
from app.models.usage import UsageRecord
from app.utils.time import utcnow

logger = get_logger("app.services.risk")


async def _recent_open_exists(
    session: AsyncSession,
    *,
    type: str,
    since: datetime,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> bool:
    conds = [RiskEvent.type == type, RiskEvent.status == RiskStatus.OPEN, RiskEvent.ts >= since]
    if user_id is not None:
        conds.append(RiskEvent.user_id == user_id)
    if organization_id is not None:
        conds.append(RiskEvent.organization_id == organization_id)
    n = int((await session.execute(select(func.count()).select_from(RiskEvent).where(*conds))).scalar() or 0)
    return n > 0


async def _open_event(
    session: AsyncSession,
    *,
    type: str,
    severity: str,
    score: float,
    detail: dict,
    since: datetime,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> RiskEvent | None:
    if await _recent_open_exists(
        session, type=type, since=since, user_id=user_id, organization_id=organization_id
    ):
        return None
    event = RiskEvent(
        user_id=user_id, organization_id=organization_id, type=type,
        severity=severity, score=round(float(score), 3), status=RiskStatus.OPEN, detail=detail,
    )
    session.add(event)
    await session.flush()
    logger.info("risk_event_opened",
                extra={"type": type, "user_id": user_id, "organization_id": organization_id,
                       "severity": severity, "score": event.score})
    return event


# --- detectors ---------------------------------------------------------------
async def detect_rapid_key_creation(
    session: AsyncSession, *, window_hours: int = 1, threshold: int = 5
) -> int:
    """Flag users who created an unusual number of API keys in a short window."""
    since = utcnow() - timedelta(hours=window_hours)
    rows = (
        await session.execute(
            select(ApiKey.user_id, func.count().label("n"))
            .where(ApiKey.created_at >= since)
            .group_by(ApiKey.user_id)
            .having(func.count() >= threshold)
        )
    ).all()
    opened = 0
    for user_id, n in rows:
        severity = Severity.HIGH if n >= threshold * 2 else Severity.MEDIUM
        ev = await _open_event(
            session, type=RiskEventType.RAPID_KEY_CREATION, severity=severity,
            score=min(1.0, n / (threshold * 2)),
            detail={"keys_created": int(n), "window_hours": window_hours, "threshold": threshold},
            since=since, user_id=user_id,
        )
        opened += 1 if ev is not None else 0
    return opened


async def detect_repeated_failed_logins(
    session: AsyncSession, *, window_minutes: int = 30, threshold: int = 5
) -> int:
    """Flag users with repeated failed logins (potential credential stuffing)."""
    since = utcnow() - timedelta(minutes=window_minutes)
    rows = (
        await session.execute(
            select(SecurityEvent.user_id, func.count().label("n"))
            .where(
                SecurityEvent.type == SecurityEventType.LOGIN_FAILED,
                SecurityEvent.ts >= since,
                SecurityEvent.user_id.is_not(None),
            )
            .group_by(SecurityEvent.user_id)
            .having(func.count() >= threshold)
        )
    ).all()
    opened = 0
    for user_id, n in rows:
        severity = Severity.HIGH if n >= threshold * 2 else Severity.MEDIUM
        ev = await _open_event(
            session, type=RiskEventType.REPEATED_FAILED_LOGINS, severity=severity,
            score=min(1.0, n / (threshold * 2)),
            detail={"failed_logins": int(n), "window_minutes": window_minutes, "threshold": threshold},
            since=since, user_id=user_id,
        )
        opened += 1 if ev is not None else 0
    return opened


async def _org_tokens(session: AsyncSession, *, since: datetime, until: datetime) -> dict[str, int]:
    rows = (
        await session.execute(
            select(UsageRecord.organization_id, func.coalesce(func.sum(UsageRecord.total_tokens), 0))
            .where(
                UsageRecord.ts >= since, UsageRecord.ts < until,
                UsageRecord.organization_id.is_not(None),
            )
            .group_by(UsageRecord.organization_id)
        )
    ).all()
    return {org_id: int(total or 0) for org_id, total in rows}


async def detect_usage_spike(
    session: AsyncSession,
    *,
    window_hours: int = 1,
    baseline_hours: int = 24,
    factor: float = 5.0,
    floor_tokens: int = 100_000,
) -> int:
    """Flag orgs whose recent token usage far exceeds their own recent baseline."""
    now = utcnow()
    win_start = now - timedelta(hours=window_hours)
    base_start = win_start - timedelta(hours=baseline_hours)

    recent = await _org_tokens(session, since=win_start, until=now)
    baseline = await _org_tokens(session, since=base_start, until=win_start)

    opened = 0
    for org_id, recent_tokens in recent.items():
        if recent_tokens < floor_tokens:
            continue
        avg_hourly = baseline.get(org_id, 0) / max(1, baseline_hours)
        threshold = max(floor_tokens, avg_hourly * factor * window_hours)
        if recent_tokens <= threshold:
            continue
        ratio = recent_tokens / max(1.0, avg_hourly * window_hours)
        severity = Severity.HIGH if ratio >= factor * 2 else Severity.MEDIUM
        ev = await _open_event(
            session, type=RiskEventType.USAGE_SPIKE, severity=severity,
            score=min(1.0, ratio / (factor * 2)),
            detail={
                "recent_tokens": recent_tokens,
                "baseline_avg_hourly": round(avg_hourly, 1),
                "ratio": round(ratio, 2),
                "window_hours": window_hours,
            },
            since=win_start, organization_id=org_id,
        )
        opened += 1 if ev is not None else 0
    return opened


async def run_sweeps(session: AsyncSession) -> dict:
    """Run every detector once (maintenance loop entry point)."""
    result = {
        "rapid_key_creation": await detect_rapid_key_creation(session),
        "repeated_failed_logins": await detect_repeated_failed_logins(session),
        "usage_spike": await detect_usage_spike(session),
    }
    total = sum(result.values())
    if total:
        logger.info("risk_sweeps_ran", extra=result)
    return result


# --- reads / review ----------------------------------------------------------
async def list_events(
    session: AsyncSession,
    *,
    organization_id: str | None = None,
    user_id: str | None = None,
    type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RiskEvent], int]:
    conds = []
    if organization_id is not None:
        conds.append(RiskEvent.organization_id == organization_id)
    if user_id is not None:
        conds.append(RiskEvent.user_id == user_id)
    if type is not None:
        conds.append(RiskEvent.type == type)
    if status is not None:
        conds.append(RiskEvent.status == status)
    total = int(
        (await session.execute(select(func.count()).select_from(RiskEvent).where(*conds))).scalar() or 0
    )
    rows = (
        await session.execute(
            select(RiskEvent).where(*conds)
            .order_by(RiskEvent.ts.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def get_event(session: AsyncSession, event_id: str) -> RiskEvent | None:
    return await session.get(RiskEvent, event_id)


async def review(
    session: AsyncSession,
    event: RiskEvent,
    *,
    status: str = RiskStatus.REVIEWED,
    reviewed_by: str | None = None,
) -> RiskEvent:
    event.status = status
    event.reviewed_by = reviewed_by
    event.reviewed_at = utcnow()
    await session.flush()
    return event
