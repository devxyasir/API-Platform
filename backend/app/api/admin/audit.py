"""Audit log viewer (administrators only)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_admin
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.common import Page

router = APIRouter(tags=["Audit"], prefix="/audit")


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_id: str | None = None
    actor_email: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    meta: dict
    ip_hash: str | None = None
    ts: datetime


@router.get("", response_model=Page[AuditOut], summary="List audit log entries")
async def list_audit(
    action: str | None = None,
    actor_id: str | None = None,
    target_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if actor_id:
        filters.append(AuditLog.actor_id == actor_id)
    if target_type:
        filters.append(AuditLog.target_type == target_type)
    if since:
        filters.append(AuditLog.ts >= since)
    if until:
        filters.append(AuditLog.ts <= until)

    total = int(
        (await session.execute(select(func.count()).select_from(AuditLog).where(*filters))).scalar() or 0
    )
    result = await session.execute(
        select(AuditLog).where(*filters).order_by(AuditLog.ts.desc()).limit(limit).offset(offset)
    )
    rows = list(result.scalars().all())
    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )
