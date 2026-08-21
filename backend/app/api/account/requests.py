"""Your request history (``/account/requests``).

Browse and inspect your own API requests. Always filtered to ``user_id == caller`` — an
account can never see another account's requests. (Admins browse every request via
``/admin/requests``.) Response/request bodies appear only when content logging was enabled
and were redacted before storage.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Reuse the response projections from the admin explorer — plain Pydantic models, no
# behaviour — so the two surfaces stay in lock-step.
from app.api.admin.requests import RequestDetailOut, RequestOut
from app.database import get_session
from app.dependencies import get_current_user
from app.errors import NotFoundError
from app.models.request_log import RequestLog
from app.models.user import User
from app.schemas.common import Page

router = APIRouter(tags=["Account Requests"], prefix="/requests")


@router.get("", response_model=Page[RequestOut], summary="List your requests")
async def list_requests(
    project_id: str | None = None,
    api_key_id: str | None = None,
    model: str | None = None,
    status: str | None = None,
    endpoint: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    filters = [RequestLog.user_id == user.id]  # hard self-scope
    if project_id:
        filters.append(RequestLog.project_id == project_id)
    if api_key_id:
        filters.append(RequestLog.api_key_id == api_key_id)
    if model:
        filters.append(RequestLog.model == model)
    if status:
        filters.append(RequestLog.status == status)
    if endpoint:
        filters.append(RequestLog.endpoint == endpoint)
    if since:
        filters.append(RequestLog.started_at >= since)
    if until:
        filters.append(RequestLog.started_at <= until)

    total = int(
        (await session.execute(select(func.count()).select_from(RequestLog).where(*filters))).scalar() or 0
    )
    result = await session.execute(
        select(RequestLog).where(*filters).order_by(RequestLog.started_at.desc()).limit(limit).offset(offset)
    )
    rows = list(result.scalars().all())
    return Page[RequestOut](
        items=[RequestOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{request_id}", response_model=RequestDetailOut, summary="Get one of your requests")
async def get_request(
    request_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(RequestLog, request_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Request not found.")
    return RequestDetailOut.model_validate(row)
