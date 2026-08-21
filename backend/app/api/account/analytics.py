"""Your usage analytics (``/account/analytics``).

Summary / time-series / breakdown metrics computed from the indexed ``requests`` table,
always filtered to the caller's own data. (Deployment-wide analytics are admin-only, at
``/admin/analytics``.)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service as analytics
from app.database import get_session
from app.dependencies import get_current_user
from app.errors import InvalidRequestError
from app.models.user import User
from app.utils.time import utcnow

router = APIRouter(tags=["Account Analytics"], prefix="/analytics")

# No ``user_id`` dimension here — the view is a single user, so it would be constant.
_BREAKDOWN_FIELDS = {"model", "endpoint", "status", "provider", "api_format"}


def _filters(
    user: User, *, days: int, since: datetime | None, until: datetime | None,
    project_id: str | None = None, model: str | None = None,
) -> analytics.Filters:
    end = until or utcnow()
    start = since or (end - timedelta(days=days))
    # Hard-pinned to the caller: an account can only ever see its own metrics.
    return analytics.Filters(
        since=start, until=end, user_id=user.id, project_id=project_id, model=model
    )


@router.get("/overview", summary="Your summary metrics")
async def overview(
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    project_id: str | None = None,
    model: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    f = _filters(user, days=days, since=since, until=until, project_id=project_id, model=model)
    data = await analytics.overview(session, f)
    return {"range": {"since": f.since.isoformat(), "until": f.until.isoformat()}, **data}


@router.get("/timeseries", summary="Your time-bucketed metrics")
async def timeseries(
    bucket: str = Query(default="day", pattern="^(hour|day)$"),
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    project_id: str | None = None,
    model: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    f = _filters(user, days=days, since=since, until=until, project_id=project_id, model=model)
    return {"bucket": bucket, "points": await analytics.timeseries(session, f, bucket=bucket)}


@router.get("/breakdown", summary="Group your metrics by a dimension")
async def breakdown(
    field: str = Query(default="model"),
    days: int = Query(default=30, ge=1, le=365),
    since: datetime | None = None,
    until: datetime | None = None,
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if field not in _BREAKDOWN_FIELDS:
        raise InvalidRequestError(
            f"Invalid breakdown field. Choose one of: {', '.join(sorted(_BREAKDOWN_FIELDS))}.",
            code="invalid_field",
        )
    f = _filters(user, days=days, since=since, until=until, project_id=project_id)
    return {"field": field, "groups": await analytics.breakdown(session, f, field)}
