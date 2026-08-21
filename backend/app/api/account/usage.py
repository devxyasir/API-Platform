"""Your usage & quota (``/account/usage``).

Reads over the append-only ``usage_records`` billing source of truth, scoped to the
caller's personal organization: the monthly token-quota status, an aggregate summary and
a per-model rollup. Read-only — usage rows are never mutated here.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.account.deps import get_account_org, resolve_plan_slug
from app.database import get_session
from app.dependencies import get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.services import quota_service, usage_service
from app.utils.time import utcnow

router = APIRouter(tags=["Account Usage"], prefix="/usage")


@router.get("/quota", summary="Your monthly token quota status")
async def quota(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    plan_slug = await resolve_plan_slug(session, org=org, user=user)
    return await quota_service.quota_status(
        session, organization_id=org.id, plan_slug=plan_slug, user_id=user.id
    )


@router.get("/summary", summary="Aggregate usage for a window")
async def summary(
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    end = until or utcnow()
    start = since or (end - timedelta(days=days))
    data = await usage_service.summary(
        session, organization_id=org.id, since=start, until=end
    )
    return {"range": {"since": start.isoformat(), "until": end.isoformat()}, **data}


@router.get("/by-model", summary="Per-model usage rollup for a window")
async def by_model(
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    end = until or utcnow()
    start = since or (end - timedelta(days=days))
    groups = await usage_service.usage_by_model(
        session, organization_id=org.id, since=start, until=end
    )
    return {"range": {"since": start.isoformat(), "until": end.isoformat()}, "groups": groups}
