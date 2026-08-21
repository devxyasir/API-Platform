"""Usage summary for API consumers (/v1/usage) — scoped to the caller's own data."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service as analytics
from app.database import get_session
from app.dependencies import AuthContext, require_scope
from app.utils.time import utcnow

router = APIRouter(tags=["Usage"])


@router.get("/usage", summary="Get your usage summary")
async def get_usage(
    days: int = Query(default=30, ge=1, le=365),
    ctx: AuthContext = Depends(require_scope("usage:read")),
    session: AsyncSession = Depends(get_session),
):
    f = analytics.Filters(
        since=utcnow() - timedelta(days=days),
        until=utcnow(),
        user_id=ctx.user.id,
    )
    overview = await analytics.overview(session, f)
    by_model = await analytics.breakdown(session, f, "model")
    series = await analytics.timeseries(session, f, bucket="day")
    return {
        "range_days": days,
        "user_id": ctx.user.id,
        "summary": overview,
        "by_model": by_model,
        "timeseries": series,
    }
