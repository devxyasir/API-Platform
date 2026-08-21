"""Rate-limit configuration, limit overrides and throttling events (§24).

Two override mechanisms sit on top of plan defaults:
- **Rate-limit configs** (``rate_limit_configs``): per-scope rpm/tpm/... merged by the
  rate-limit resolver into the request's ``LimitSet``.
- **Limit overrides** (``limit_overrides``): time-boxed, reason-tagged single-metric
  overrides (e.g. a temporary ``monthly_token_quota`` bump) resolved at highest
  precedence by ``limit_service`` — used by both rate limiting and quota enforcement.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError, NotFoundError
from app.models.rate_limit import RateLimitConfig, RateLimitEvent
from app.models.user import User
from app.schemas.admin import (
    LimitOverrideCreate,
    LimitOverrideOut,
    RateLimitConfigIn,
    RateLimitConfigOut,
)
from app.schemas.common import OK
from app.services import audit_service, limit_service
from app.services.limits_resolver import PLAN_LIMITS

router = APIRouter(tags=["Rate Limits"], prefix="/rate-limits")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


class RateLimitEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str | None = None
    project_id: str | None = None
    api_key_id: str | None = None
    limit_type: str
    scope: str
    limit_value: int
    ts: datetime


@router.get("/plan-defaults", summary="Built-in per-plan default limits")
async def plan_defaults(_admin: User = Depends(require_permission("limits.read"))):
    return {plan: asdict(limits) for plan, limits in PLAN_LIMITS.items()}


@router.get("/configs", response_model=list[RateLimitConfigOut], summary="List limit overrides")
async def list_configs(
    _admin: User = Depends(require_permission("limits.read")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(RateLimitConfig).order_by(RateLimitConfig.scope_type))
    return [RateLimitConfigOut.model_validate(c) for c in result.scalars().all()]


@router.put("/configs", response_model=RateLimitConfigOut, summary="Create or update a limit override")
async def upsert_config(
    body: RateLimitConfigIn,
    request: Request,
    admin: User = Depends(require_permission("limits.write")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RateLimitConfig).where(
            RateLimitConfig.scope_type == body.scope_type,
            RateLimitConfig.scope_id == body.scope_id,
        )
    )
    config = result.scalar_one_or_none()
    fields = body.model_dump()
    if config is None:
        config = RateLimitConfig(**fields)
        session.add(config)
    else:
        for key, value in fields.items():
            setattr(config, key, value)
    await session.flush()
    await audit_service.record_audit(
        session, action="rate_limit.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="rate_limit_config", target_id=config.id,
        meta={"scope_type": body.scope_type, "scope_id": body.scope_id}, ip_hash=_ip(request),
    )
    return RateLimitConfigOut.model_validate(config)


@router.delete("/configs/{config_id}", response_model=OK, summary="Delete a limit override")
async def delete_config(
    config_id: str,
    request: Request,
    admin: User = Depends(require_permission("limits.write")),
    session: AsyncSession = Depends(get_session),
):
    config = await session.get(RateLimitConfig, config_id)
    if config is None:
        raise NotFoundError("Rate-limit config not found.")
    await session.delete(config)
    await session.flush()
    await audit_service.record_audit(
        session, action="rate_limit.deleted", actor_id=admin.id, actor_email=admin.email,
        target_type="rate_limit_config", target_id=config_id, ip_hash=_ip(request),
    )
    return OK(detail="Rate-limit override deleted.")


# --- time-boxed limit overrides (§24) ----------------------------------------
@router.get("/overrides", response_model=list[LimitOverrideOut], summary="List limit overrides")
async def list_overrides(
    scope_type: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    include_expired: bool = Query(default=True),
    _admin: User = Depends(require_permission("limits.read")),
    session: AsyncSession = Depends(get_session),
):
    rows = await limit_service.list_overrides(
        session, scope_type=scope_type, scope_id=scope_id, include_expired=include_expired
    )
    return [LimitOverrideOut.model_validate(r) for r in rows]


@router.post(
    "/overrides",
    response_model=LimitOverrideOut,
    status_code=201,
    summary="Create a time-boxed limit override",
)
async def create_override(
    body: LimitOverrideCreate,
    request: Request,
    admin: User = Depends(require_permission("limits.write")),
    session: AsyncSession = Depends(get_session),
):
    if not limit_service.is_known_metric(body.metric):
        raise InvalidRequestError(
            f"Unknown limit metric '{body.metric}'.", code="invalid_limit_metric"
        )
    override = await limit_service.create_override(
        session, scope_type=body.scope_type, scope_id=body.scope_id, metric=body.metric,
        value=body.value, expires_at=body.expires_at, reason=body.reason, created_by=admin.id,
    )
    await audit_service.record_audit(
        session, action="limit_override.created", actor_id=admin.id, actor_email=admin.email,
        target_type="limit_override", target_id=override.id,
        meta={"scope_type": body.scope_type, "scope_id": body.scope_id, "metric": body.metric,
              "value": body.value}, ip_hash=_ip(request),
    )
    return LimitOverrideOut.model_validate(override)


@router.delete("/overrides/{override_id}", response_model=OK, summary="Delete a limit override")
async def delete_override(
    override_id: str,
    request: Request,
    admin: User = Depends(require_permission("limits.write")),
    session: AsyncSession = Depends(get_session),
):
    await limit_service.delete_override(session, override_id)
    await audit_service.record_audit(
        session, action="limit_override.deleted", actor_id=admin.id, actor_email=admin.email,
        target_type="limit_override", target_id=override_id, ip_hash=_ip(request),
    )
    return OK(detail="Limit override deleted.")


@router.get("/events", response_model=list[RateLimitEventOut], summary="Recent throttling events")
async def list_events(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: User = Depends(require_permission("limits.read")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RateLimitEvent).order_by(RateLimitEvent.ts.desc()).limit(limit)
    )
    return [RateLimitEventOut.model_validate(e) for e in result.scalars().all()]
