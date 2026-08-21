"""Plan catalogue operations (§8-12).

Plans live in the database. This service reads/writes plans and their structured
limits, feature flags, and model allow-lists, using explicit queries (never lazy
relationship access, which is unsafe under async). Plans with billing history are
soft-archived, never hard-deleted (§53)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import ConflictError, NotFoundError
from app.models.plan import Plan, PlanFeature, PlanLimit, PlanModel


async def get_plan(session: AsyncSession, plan_id: str) -> Plan | None:
    return await session.get(Plan, plan_id)


async def get_plan_by_slug(session: AsyncSession, slug: str) -> Plan | None:
    return (
        await session.execute(select(Plan).where(Plan.slug == slug))
    ).scalar_one_or_none()


async def get_plan_or_404(session: AsyncSession, plan_id: str) -> Plan:
    plan = await get_plan(session, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found.", code="plan_not_found")
    return plan


async def list_plans(
    session: AsyncSession, *, include_archived: bool = False, only_public: bool = False
) -> list[Plan]:
    stmt = select(Plan)
    if not include_archived:
        stmt = stmt.where(Plan.archived.is_(False))
    if only_public:
        stmt = stmt.where(Plan.is_public.is_(True))
    stmt = stmt.order_by(Plan.sort_order, Plan.name)
    return list((await session.execute(stmt)).scalars().all())


async def default_plan(session: AsyncSession) -> Plan | None:
    """The plan assigned to new accounts (config default slug, else first active)."""
    plan = await get_plan_by_slug(session, settings.default_plan_slug)
    if plan is not None:
        return plan
    return (
        await session.execute(
            select(Plan).where(Plan.active.is_(True), Plan.archived.is_(False))
            .order_by(Plan.sort_order)
        )
    ).scalars().first()


# --- limits / features / models (explicit queries) --------------------------
async def limit_map(session: AsyncSession, plan_id: str) -> dict[str, int | None]:
    """{metric: value} for a plan. A metric with no row is unlimited (absent here)."""
    rows = (
        await session.execute(select(PlanLimit).where(PlanLimit.plan_id == plan_id))
    ).scalars().all()
    return {r.metric: r.value for r in rows}


async def feature_map(session: AsyncSession, plan_id: str) -> dict[str, Any]:
    """{key: value} for a plan (unwrapping the stored {"value": ...} envelope)."""
    rows = (
        await session.execute(select(PlanFeature).where(PlanFeature.plan_id == plan_id))
    ).scalars().all()
    out: dict[str, Any] = {}
    for r in rows:
        v = r.value
        out[r.key] = v.get("value") if isinstance(v, dict) and "value" in v else v
    return out


async def allowed_models(session: AsyncSession, plan_id: str) -> list[str]:
    rows = (
        await session.execute(select(PlanModel).where(PlanModel.plan_id == plan_id))
    ).scalars().all()
    return [r.model_public_id for r in rows]


async def model_allowed(session: AsyncSession, plan_id: str, model_public_id: str) -> bool:
    """True if the plan permits the model. An empty allow-list means all models (§55)."""
    allow = await allowed_models(session, plan_id)
    if not allow:
        return True
    return model_public_id in allow


# --- admin mutations ---------------------------------------------------------
async def create_plan(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    description: str = "",
    price_monthly_usd: float = 0.0,
    price_yearly_usd: float = 0.0,
    monthly_credits: int = 0,
    trial_days: int = 0,
    sort_order: int = 0,
    is_public: bool = True,
    limits: dict[str, int | None] | None = None,
    features: dict[str, Any] | None = None,
    models: list[str] | None = None,
) -> Plan:
    if await get_plan_by_slug(session, slug) is not None:
        raise ConflictError("A plan with that slug already exists.", code="plan_slug_taken")
    plan = Plan(
        slug=slug, name=name, description=description,
        price_monthly_usd=price_monthly_usd, price_yearly_usd=price_yearly_usd,
        monthly_credits=monthly_credits, trial_days=trial_days,
        sort_order=sort_order, is_public=is_public, active=True, archived=False,
    )
    session.add(plan)
    await session.flush()
    if limits:
        await set_limits(session, plan.id, limits)
    if features:
        await set_features(session, plan.id, features)
    if models is not None:
        await set_models(session, plan.id, models)
    await session.flush()
    return plan


async def set_limits(session: AsyncSession, plan_id: str, limits: dict[str, int | None]) -> None:
    """Replace a plan's limit rows with the given map (None value = unlimited row)."""
    existing = {
        r.metric: r
        for r in (await session.execute(select(PlanLimit).where(PlanLimit.plan_id == plan_id))).scalars()
    }
    for metric, value in limits.items():
        if metric in existing:
            existing[metric].value = value
        else:
            session.add(PlanLimit(plan_id=plan_id, metric=metric, value=value))
    # Drop metrics no longer present.
    for metric, row in existing.items():
        if metric not in limits:
            await session.delete(row)
    await session.flush()


async def set_features(session: AsyncSession, plan_id: str, features: dict[str, Any]) -> None:
    existing = {
        r.key: r
        for r in (await session.execute(select(PlanFeature).where(PlanFeature.plan_id == plan_id))).scalars()
    }
    for key, value in features.items():
        wrapped = {"value": value}
        if key in existing:
            existing[key].value = wrapped
        else:
            session.add(PlanFeature(plan_id=plan_id, key=key, value=wrapped))
    for key, row in existing.items():
        if key not in features:
            await session.delete(row)
    await session.flush()


async def set_models(session: AsyncSession, plan_id: str, models: list[str]) -> None:
    """Replace a plan's model allow-list (empty list = all models allowed)."""
    existing_map = {
        r.model_public_id: r
        for r in (await session.execute(select(PlanModel).where(PlanModel.plan_id == plan_id))).scalars()
    }
    wanted = list(dict.fromkeys(models))  # de-dupe, preserve order

    # Drop removed models
    for public_id, row in existing_map.items():
        if public_id not in wanted:
            await session.delete(row)

    # Add only new models
    for public_id in wanted:
        if public_id not in existing_map:
            session.add(PlanModel(plan_id=plan_id, model_public_id=public_id))

    await session.flush()


async def archive_plan(session: AsyncSession, plan: Plan) -> None:
    """Soft-archive: keep history intact, hide from new subscriptions (§53)."""
    plan.archived = True
    plan.active = False
    plan.is_public = False
    await session.flush()


async def count_plans(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Plan))).scalar() or 0)
