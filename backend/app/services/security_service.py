"""Security events (§41) — an append-only log of authentication / access-control
findings (login success/failure, key lifecycle, permission denials, suspicious logins).

Recording never raises into the caller's flow: a security-log failure must not break a
login or an API call, so :func:`record` swallows and logs its own errors."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models.enums import SecurityEventStatus, Severity
from app.models.security import SecurityEvent
from app.utils.time import utcnow

logger = get_logger("app.services.security")


async def record(
    session: AsyncSession,
    *,
    type: str,
    user_id: str | None = None,
    organization_id: str | None = None,
    severity: str = Severity.INFO,
    ip_hash: str | None = None,
    user_agent: str | None = None,
    meta: dict | None = None,
) -> SecurityEvent | None:
    """Append a security event. Returns None (and logs) if persistence fails, so the
    caller's primary operation is never disrupted by security logging."""
    try:
        event = SecurityEvent(
            user_id=user_id,
            organization_id=organization_id,
            type=type,
            status=SecurityEventStatus.OPEN,
            severity=severity,
            ip_hash=ip_hash,
            user_agent=(user_agent or None) if user_agent is None else user_agent[:400],
            meta=meta or {},
        )
        session.add(event)
        await session.flush()
        return event
    except Exception:  # pragma: no cover - defensive
        logger.exception("security_event_record_failed", extra={"type": type})
        return None


async def list_events(
    session: AsyncSession,
    *,
    user_id: str | None = None,
    organization_id: str | None = None,
    type: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SecurityEvent], int]:
    conds = []
    if user_id is not None:
        conds.append(SecurityEvent.user_id == user_id)
    if organization_id is not None:
        conds.append(SecurityEvent.organization_id == organization_id)
    if type is not None:
        conds.append(SecurityEvent.type == type)
    if status is not None:
        conds.append(SecurityEvent.status == status)
    if severity is not None:
        conds.append(SecurityEvent.severity == severity)
    total = int(
        (await session.execute(select(func.count()).select_from(SecurityEvent).where(*conds))).scalar() or 0
    )
    rows = (
        await session.execute(
            select(SecurityEvent).where(*conds)
            .order_by(SecurityEvent.ts.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def resolve(
    session: AsyncSession,
    event: SecurityEvent,
    *,
    resolved_by: str | None = None,
    status: str = SecurityEventStatus.RESOLVED,
) -> SecurityEvent:
    event.status = status
    event.resolved_at = utcnow()
    event.resolved_by = resolved_by
    await session.flush()
    return event


async def count_events(
    session: AsyncSession,
    *,
    type: str,
    since: datetime,
    user_id: str | None = None,
    ip_hash: str | None = None,
) -> int:
    """Count events of a type in a window (used by the risk-detection sweeps)."""
    conds = [SecurityEvent.type == type, SecurityEvent.ts >= since]
    if user_id is not None:
        conds.append(SecurityEvent.user_id == user_id)
    if ip_hash is not None:
        conds.append(SecurityEvent.ip_hash == ip_hash)
    return int((await session.execute(select(func.count()).select_from(SecurityEvent).where(*conds))).scalar() or 0)


async def get_event(session: AsyncSession, event_id: str) -> SecurityEvent | None:
    return await session.get(SecurityEvent, event_id)
