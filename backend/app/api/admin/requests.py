"""Request explorer: browse and inspect individual API requests (platform-wide).

The admin control-plane view of **every** request across all accounts, with optional
filters. Requires an admin-scoped session and ``usage.read`` — a user-scoped token is
rejected. Users browse their own request history via ``/account/requests``.
Request/response bodies are surfaced only when they were captured (``LOG_REQUEST_CONTENT``
enabled) and were redacted before storage.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import NotFoundError
from app.models.request_log import RequestLog
from app.models.user import User
from app.schemas.common import Page

router = APIRouter(tags=["Requests"], prefix="/requests")


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str | None = None
    project_id: str | None = None
    api_key_id: str | None = None
    model: str | None = None
    upstream_model: str | None = None
    endpoint: str
    method: str
    api_format: str
    provider: str
    status: str
    status_code: int
    stream: bool
    started_at: datetime
    completed_at: datetime | None = None
    latency_ms: float
    ttft_ms: float | None = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    token_count_source: str
    provider_request_id: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class RequestDetailOut(RequestOut):
    ip_hash: str | None = None
    user_agent: str | None = None
    request_content: str | None = None
    response_content: str | None = None


@router.get("", response_model=Page[RequestOut], summary="List requests")
async def list_requests(
    user_id: str | None = None,
    project_id: str | None = None,
    api_key_id: str | None = None,
    model: str | None = None,
    status: str | None = None,
    endpoint: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    filters = []
    if user_id:
        filters.append(RequestLog.user_id == user_id)
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


@router.get("/{request_id}", response_model=RequestDetailOut, summary="Get a request")
async def get_request(
    request_id: str,
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(RequestLog, request_id)
    if row is None:
        raise NotFoundError("Request not found.")
    return RequestDetailOut.model_validate(row)
