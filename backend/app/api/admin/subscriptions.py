"""Subscription administration (§31, §12).

A subscription binds an organization to a plan over billing periods. Plan changes are
recorded in an append-only ``PlanHistory`` (§12); no real payment provider is contacted
(billing is simulated — see billing.py / billing_service)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError
from app.models.enums import SubscriptionStatus
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.admin import (
    PlanHistoryOut,
    SubscriptionCancel,
    SubscriptionChangePlan,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionStatusUpdate,
)
from app.schemas.common import OK, Page
from app.services import (
    audit_service,
    organization_service,
    plan_service,
    subscription_service,
)

router = APIRouter(tags=["Subscriptions"], prefix="/subscriptions")

_VALID_STATUS = {s.value for s in SubscriptionStatus}


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


async def _sub_out(session: AsyncSession, sub: Subscription) -> SubscriptionOut:
    """Project a subscription with its plan slug/name folded in for convenience."""
    plan = await session.get(Plan, sub.plan_id)
    out = SubscriptionOut.model_validate(sub)
    if plan is not None:
        out.plan_slug = plan.slug
        out.plan_name = plan.name
    return out


@router.get("", response_model=Page[SubscriptionOut], summary="List subscriptions")
async def list_subscriptions(
    organization_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("subscriptions.read")),
    session: AsyncSession = Depends(get_session),
):
    subs, total = await subscription_service.list_subscriptions(
        session, organization_id=organization_id, status=status, limit=limit, offset=offset
    )
    return Page[SubscriptionOut](
        items=[await _sub_out(session, s) for s in subs], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=SubscriptionOut, status_code=201, summary="Create a subscription")
async def create_subscription(
    body: SubscriptionCreate,
    request: Request,
    admin: User = Depends(require_permission("subscriptions.write")),
    session: AsyncSession = Depends(get_session),
):
    org = await organization_service.get_org_or_404(session, body.organization_id)
    plan = await plan_service.get_plan_or_404(session, body.plan_id)
    existing = await subscription_service.get_active_subscription(session, org.id)
    if existing is not None:
        raise InvalidRequestError(
            "This organization already has a subscription; change its plan instead.",
            code="subscription_exists",
        )
    sub = await subscription_service.create_subscription(
        session, organization_id=org.id, plan=plan, actor_id=admin.id,
        user_id=org.owner_id, trial=body.trial, reason=body.reason,
    )
    await audit_service.record_audit(
        session, action="subscription.created", actor_id=admin.id, actor_email=admin.email,
        target_type="subscription", target_id=sub.id,
        meta={"organization_id": org.id, "plan": plan.slug}, ip_hash=_ip(request),
    )
    return await _sub_out(session, sub)


@router.get("/{subscription_id}", response_model=SubscriptionOut, summary="Get a subscription")
async def get_subscription(
    subscription_id: str,
    _admin: User = Depends(require_permission("subscriptions.read")),
    session: AsyncSession = Depends(get_session),
):
    sub = await subscription_service.get_or_404(session, subscription_id)
    return await _sub_out(session, sub)


@router.post("/{subscription_id}/change-plan", response_model=SubscriptionOut, summary="Change plan")
async def change_plan(
    subscription_id: str,
    body: SubscriptionChangePlan,
    request: Request,
    admin: User = Depends(require_permission("subscriptions.write")),
    session: AsyncSession = Depends(get_session),
):
    sub = await subscription_service.get_or_404(session, subscription_id)
    new_plan = await plan_service.get_plan_or_404(session, body.plan_id)
    sub = await subscription_service.change_plan(
        session, sub, new_plan, actor_id=admin.id, reason=body.reason,
        grant_credits=body.grant_credits,
    )
    await audit_service.record_audit(
        session, action="subscription.plan_changed", actor_id=admin.id, actor_email=admin.email,
        target_type="subscription", target_id=sub.id,
        meta={"plan": new_plan.slug, "reason": body.reason}, ip_hash=_ip(request),
    )
    return await _sub_out(session, sub)


@router.post("/{subscription_id}/status", response_model=SubscriptionOut, summary="Set status")
async def set_status(
    subscription_id: str,
    body: SubscriptionStatusUpdate,
    request: Request,
    admin: User = Depends(require_permission("subscriptions.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.status not in _VALID_STATUS:
        raise InvalidRequestError(
            f"Invalid subscription status. Choose one of: {', '.join(sorted(_VALID_STATUS))}.",
            code="invalid_status",
        )
    sub = await subscription_service.get_or_404(session, subscription_id)
    sub = await subscription_service.set_status(session, sub, body.status)
    await audit_service.record_audit(
        session, action="subscription.status_changed", actor_id=admin.id, actor_email=admin.email,
        target_type="subscription", target_id=sub.id,
        meta={"status": body.status}, ip_hash=_ip(request),
    )
    return await _sub_out(session, sub)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionOut, summary="Cancel a subscription")
async def cancel_subscription(
    subscription_id: str,
    body: SubscriptionCancel,
    request: Request,
    admin: User = Depends(require_permission("subscriptions.write")),
    session: AsyncSession = Depends(get_session),
):
    sub = await subscription_service.get_or_404(session, subscription_id)
    sub = await subscription_service.cancel(
        session, sub, at_period_end=body.at_period_end, actor_id=admin.id
    )
    await audit_service.record_audit(
        session, action="subscription.cancelled", actor_id=admin.id, actor_email=admin.email,
        target_type="subscription", target_id=sub.id,
        meta={"at_period_end": body.at_period_end}, ip_hash=_ip(request),
    )
    return await _sub_out(session, sub)


@router.get(
    "/history/{organization_id}",
    response_model=Page[PlanHistoryOut],
    summary="Plan-change history for an organization",
)
async def plan_history(
    organization_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("subscriptions.read")),
    session: AsyncSession = Depends(get_session),
):
    await organization_service.get_org_or_404(session, organization_id)
    rows, total = await subscription_service.plan_history(
        session, organization_id, limit=limit, offset=offset
    )
    return Page[PlanHistoryOut](
        items=[PlanHistoryOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )
