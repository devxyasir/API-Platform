"""Audit logging for security-sensitive administrative events."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_id: str | None = None,
    actor_email: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    meta: dict[str, Any] | None = None,
    ip_hash: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        actor_email=actor_email,
        target_type=target_type,
        target_id=target_id,
        meta=meta or {},
        ip_hash=ip_hash,
    )
    session.add(entry)
    await session.flush()
    return entry
