"""Deployment-wide analytics for the admin console (§35-37).

Platform-wide metrics computed from the indexed ``requests`` table, with optional filters
(user/project/model). Requires an admin-scoped session and ``usage.read`` — a user-scoped
token is rejected. Users see only their own metrics via ``/account/analytics``.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service as analytics
from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError
from app.models.user import User
from app.utils.time import utcnow

router = APIRouter(tags=["Analytics"], prefix="/analytics")

_BREAKDOWN_FIELDS = {"model", "endpoint", "user_id", "status", "provider", "api_format"}


def _filters(
    *, days: int, since: datetime | None, until: datetime | None,
    user_id: str | None = None, project_id: str | None = None, model: str | None = None,
) -> analytics.Filters:
    end = until or utcnow()
    start = since or (end - timedelta(days=days))
    return analytics.Filters(
        since=start, until=end, user_id=user_id, project_id=project_id, model=model
    )


@router.get("/overview", summary="Summary metrics (platform-wide)")
async def overview(
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    model: str | None = None,
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    f = _filters(days=days, since=since, until=until, user_id=user_id, project_id=project_id, model=model)
    data = await analytics.overview(session, f)
    active = await analytics.active_counts(session, f.since)
    return {"range": {"since": f.since.isoformat(), "until": f.until.isoformat()}, **data, **active}


@router.get("/timeseries", summary="Time-bucketed metrics (platform-wide)")
async def timeseries(
    bucket: str = Query(default="day", pattern="^(hour|day)$"),
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    model: str | None = None,
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    f = _filters(days=days, since=since, until=until, user_id=user_id, project_id=project_id, model=model)
    return {"bucket": bucket, "points": await analytics.timeseries(session, f, bucket=bucket)}


@router.get("/breakdown", summary="Group metrics by a dimension (platform-wide)")
async def breakdown(
    field: str = Query(default="model"),
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    if field not in _BREAKDOWN_FIELDS:
        raise InvalidRequestError(
            f"Invalid breakdown field. Choose one of: {', '.join(sorted(_BREAKDOWN_FIELDS))}.",
            code="invalid_field",
        )
    f = _filters(days=days, since=since, until=until, user_id=user_id, project_id=project_id)
    return {"field": field, "groups": await analytics.breakdown(session, f, field)}
