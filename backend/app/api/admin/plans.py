"""Subscription-plan administration (§8-12).

Plans live in the database with structured limits, feature flags and a model
allow-list. Plans with billing history are soft-archived, never hard-deleted (§53)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError
from app.models.enums import LIMIT_METRICS
from app.models.plan import Plan
from app.models.user import User
from app.schemas.admin import PlanCreate, PlanOut, PlanUpdate
from app.services import audit_service, plan_service

router = APIRouter(tags=["Plans"], prefix="/plans")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


def _validate_limits(limits: dict[str, int | None] | None) -> None:
    if not limits:
        return
    unknown = [m for m in limits if m not in LIMIT_METRICS]
    if unknown:
        raise InvalidRequestError(
            f"Unknown limit metric(s): {', '.join(sorted(unknown))}. "
            f"Valid metrics: {', '.join(sorted(LIMIT_METRICS))}.",
            code="invalid_limit_metric",
        )


async def _plan_out(session: AsyncSession, plan: Plan) -> PlanOut:
    """Fold a plan's separate limit/feature/model rows into a single response object."""
    return PlanOut(
        id=plan.id,
        slug=plan.slug,
        name=plan.name,
        description=plan.description,
        active=plan.active,
        archived=plan.archived,
        is_public=plan.is_public,
        price_monthly_usd=plan.price_monthly_usd,
        price_yearly_usd=plan.price_yearly_usd,
        monthly_credits=plan.monthly_credits,
        trial_days=plan.trial_days,
        sort_order=plan.sort_order,
        created_at=plan.created_at,
        limits=await plan_service.limit_map(session, plan.id),
        features=await plan_service.feature_map(session, plan.id),
        models=await plan_service.allowed_models(session, plan.id),
    )


@router.get("", response_model=list[PlanOut], summary="List plans")
async def list_plans(
    include_archived: bool = Query(default=False),
    only_public: bool = Query(default=False),
    _admin: User = Depends(require_permission("plans.read")),
    session: AsyncSession = Depends(get_session),
):
    plans = await plan_service.list_plans(
        session, include_archived=include_archived, only_public=only_public
    )
    return [await _plan_out(session, p) for p in plans]


@router.post("", response_model=PlanOut, status_code=201, summary="Create a plan")
async def create_plan(
    body: PlanCreate,
    request: Request,
    admin: User = Depends(require_permission("plans.write")),
    session: AsyncSession = Depends(get_session),
):
    _validate_limits(body.limits)
    plan = await plan_service.create_plan(
        session, slug=body.slug, name=body.name, description=body.description,
        price_monthly_usd=body.price_monthly_usd, price_yearly_usd=body.price_yearly_usd,
        monthly_credits=body.monthly_credits, trial_days=body.trial_days,
        sort_order=body.sort_order, is_public=body.is_public,
        limits=body.limits, features=body.features, models=body.models,
    )
    await audit_service.record_audit(
        session, action="plan.created", actor_id=admin.id, actor_email=admin.email,
        target_type="plan", target_id=plan.id, meta={"slug": plan.slug}, ip_hash=_ip(request),
    )
    return await _plan_out(session, plan)


@router.get("/{plan_id}", response_model=PlanOut, summary="Get a plan")
async def get_plan(
    plan_id: str,
    _admin: User = Depends(require_permission("plans.read")),
    session: AsyncSession = Depends(get_session),
):
    plan = await plan_service.get_plan_or_404(session, plan_id)
    return await _plan_out(session, plan)


@router.patch("/{plan_id}", response_model=PlanOut, summary="Update a plan")
async def update_plan(
    plan_id: str,
    body: PlanUpdate,
    request: Request,
    admin: User = Depends(require_permission("plans.write")),
    session: AsyncSession = Depends(get_session),
):
    plan = await plan_service.get_plan_or_404(session, plan_id)
    changes = body.model_dump(exclude_unset=True)
    _validate_limits(changes.get("limits"))
    # Scalar columns applied directly; the structured collections go through the service.
    scalar = {k: v for k, v in changes.items() if k not in ("limits", "features", "models")}
    for key, value in scalar.items():
        setattr(plan, key, value)
    await session.flush()
    if "limits" in changes and changes["limits"] is not None:
        await plan_service.set_limits(session, plan.id, changes["limits"])
    if "features" in changes and changes["features"] is not None:
        await plan_service.set_features(session, plan.id, changes["features"])
    if "models" in changes and changes["models"] is not None:
        await plan_service.set_models(session, plan.id, changes["models"])
    await audit_service.record_audit(
        session, action="plan.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="plan", target_id=plan.id, meta={"changes": list(changes)}, ip_hash=_ip(request),
    )
    return await _plan_out(session, plan)


@router.post("/{plan_id}/archive", response_model=PlanOut, summary="Archive a plan")
async def archive_plan(
    plan_id: str,
    request: Request,
    admin: User = Depends(require_permission("plans.write")),
    session: AsyncSession = Depends(get_session),
):
    plan = await plan_service.get_plan_or_404(session, plan_id)
    await plan_service.archive_plan(session, plan)
    await audit_service.record_audit(
        session, action="plan.archived", actor_id=admin.id, actor_email=admin.email,
        target_type="plan", target_id=plan.id, ip_hash=_ip(request),
    )
    return await _plan_out(session, plan)
