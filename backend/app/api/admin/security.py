"""Security & risk administration (§38, §41).

Two append-only queues for the trust-&-safety surface:
- **Security events** — authentication / access-control findings (logins, key lifecycle,
  permission denials). Resolvable by an operator.
- **Risk events** — output of the periodic abuse-detection sweeps (rapid key creation,
  repeated failed logins, usage spikes). Reviewable by an operator.

Neither queue is ever edited destructively; resolving/reviewing only stamps status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import NotFoundError
from app.models.enums import RiskStatus, SecurityEventStatus
from app.models.user import User
from app.schemas.admin import (
    RiskEventOut,
    RiskEventReview,
    SecurityEventOut,
    SecurityEventResolve,
)
from app.schemas.common import Page
from app.services import audit_service, risk_service, security_service

router = APIRouter(tags=["Security"], prefix="/security")

_VALID_SEC_STATUS = {s.value for s in SecurityEventStatus}
_VALID_RISK_STATUS = {s.value for s in RiskStatus}


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


# --- security events ---------------------------------------------------------
@router.get("/events", response_model=Page[SecurityEventOut], summary="List security events")
async def list_security_events(
    user_id: str | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("security.read")),
    session: AsyncSession = Depends(get_session),
):
    rows, total = await security_service.list_events(
        session, user_id=user_id, organization_id=organization_id, type=type,
        status=status, severity=severity, limit=limit, offset=offset,
    )
    return Page[SecurityEventOut](
        items=[SecurityEventOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/events/{event_id}/resolve",
    response_model=SecurityEventOut,
    summary="Resolve a security event",
)
async def resolve_security_event(
    event_id: str,
    body: SecurityEventResolve,
    request: Request,
    admin: User = Depends(require_permission("security.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.status not in _VALID_SEC_STATUS:
        raise NotFoundError("Invalid security event status.", code="invalid_status")
    event = await security_service.get_event(session, event_id)
    if event is None:
        raise NotFoundError("Security event not found.", code="security_event_not_found")
    event = await security_service.resolve(
        session, event, resolved_by=admin.id, status=body.status
    )
    await audit_service.record_audit(
        session, action="security_event.resolved", actor_id=admin.id, actor_email=admin.email,
        target_type="security_event", target_id=event.id,
        meta={"status": body.status}, ip_hash=_ip(request),
    )
    return SecurityEventOut.model_validate(event)


# --- risk events -------------------------------------------------------------
@router.get("/risk", response_model=Page[RiskEventOut], summary="List risk events")
async def list_risk_events(
    user_id: str | None = Query(default=None),
    organization_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("risk.read")),
    session: AsyncSession = Depends(get_session),
):
    rows, total = await risk_service.list_events(
        session, user_id=user_id, organization_id=organization_id, type=type,
        status=status, limit=limit, offset=offset,
    )
    return Page[RiskEventOut](
        items=[RiskEventOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/risk/{event_id}/review", response_model=RiskEventOut, summary="Review a risk event")
async def review_risk_event(
    event_id: str,
    body: RiskEventReview,
    request: Request,
    admin: User = Depends(require_permission("risk.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.status not in _VALID_RISK_STATUS:
        raise NotFoundError("Invalid risk event status.", code="invalid_status")
    event = await risk_service.get_event(session, event_id)
    if event is None:
        raise NotFoundError("Risk event not found.", code="risk_event_not_found")
    event = await risk_service.review(session, event, status=body.status, reviewed_by=admin.id)
    await audit_service.record_audit(
        session, action="risk_event.reviewed", actor_id=admin.id, actor_email=admin.email,
        target_type="risk_event", target_id=event.id,
        meta={"status": body.status}, ip_hash=_ip(request),
    )
    return RiskEventOut.model_validate(event)


@router.post("/risk/run-sweeps", summary="Run risk-detection sweeps now")
async def run_sweeps(
    request: Request,
    admin: User = Depends(require_permission("risk.write")),
    session: AsyncSession = Depends(get_session),
):
    result = await risk_service.run_sweeps(session)
    await audit_service.record_audit(
        session, action="risk.sweeps_run", actor_id=admin.id, actor_email=admin.email,
        target_type="system", target_id="risk", meta=result, ip_hash=_ip(request),
    )
    return {"opened": result, "total": sum(result.values())}
