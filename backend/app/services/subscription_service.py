"""Subscriptions bind an organization to a plan over billing periods (§31), with an
append-only plan-change history (§12) and a period/status state machine used by the
billing simulation. No real payment provider is contacted — see billing_service."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.logging_config import get_logger
from app.models.enums import SubscriptionStatus, TrialStatus
from app.models.plan import Plan
from app.models.subscription import PlanHistory, Subscription
from app.services import credit_service, plan_service
from app.utils.time import add_months, ensure_aware, utcnow

logger = get_logger("app.services.subscription")


async def get_subscription(session: AsyncSession, subscription_id: str) -> Subscription | None:
    return await session.get(Subscription, subscription_id)


async def get_active_subscription(session: AsyncSession, organization_id: str) -> Subscription | None:
    """The organization's current subscription (most recent), if any."""
    return (
        await session.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .order_by(Subscription.created_at.desc())
        )
    ).scalars().first()


async def _plan_slug(session: AsyncSession, plan_id: str) -> str | None:
    plan = await session.get(Plan, plan_id)
    return plan.slug if plan is not None else None


async def _record_history(
    session: AsyncSession,
    *,
    organization_id: str,
    old_plan: str | None,
    new_plan: str,
    changed_by: str | None,
    reason: str,
    user_id: str | None = None,
) -> None:
    session.add(
        PlanHistory(
            organization_id=organization_id,
            user_id=user_id,
            old_plan=old_plan,
            new_plan=new_plan,
            changed_by=changed_by,
            reason=reason,
        )
    )


async def create_subscription(
    session: AsyncSession,
    *,
    organization_id: str,
    plan: Plan,
    actor_id: str | None = None,
    user_id: str | None = None,
    trial: bool | None = None,
    reason: str = "initial subscription",
    grant_credits: bool = True,
) -> Subscription:
    """Create the organization's subscription to ``plan`` and record plan history.

    Starts a trial when ``trial`` is True (or None + config enabled + plan.trial_days),
    otherwise a normal monthly period. Grants the plan's opening credits (§14)."""
    now = utcnow()
    from app.config import settings  # local import avoids a config import cycle at module load

    use_trial = trial if trial is not None else (settings.trial_enabled and plan.trial_days > 0)

    if use_trial and plan.trial_days > 0:
        status = SubscriptionStatus.TRIALING
        trial_status = TrialStatus.ACTIVE
        trial_start = now
        trial_end = now + timedelta(days=plan.trial_days)
        period_end = trial_end
    else:
        status = SubscriptionStatus.ACTIVE
        trial_status = TrialStatus.NONE
        trial_start = trial_end = None
        period_end = add_months(now, 1)

    sub = Subscription(
        organization_id=organization_id,
        plan_id=plan.id,
        status=status,
        provider="manual",
        current_period_start=now,
        current_period_end=period_end,
        cancel_at_period_end=False,
        trial_status=trial_status,
        trial_start=trial_start,
        trial_end=trial_end,
    )
    session.add(sub)
    await _record_history(
        session, organization_id=organization_id, old_plan=None, new_plan=plan.slug,
        changed_by=actor_id, reason=reason, user_id=user_id,
    )
    await session.flush()

    if grant_credits and plan.monthly_credits > 0:
        await credit_service.grant(
            session, organization_id, plan.monthly_credits,
            reason=f"Opening credits for {plan.name} plan", reference_id=sub.id,
            created_by=actor_id, user_id=user_id,
        )
    logger.info("subscription_created",
                extra={"organization_id": organization_id, "plan": plan.slug, "status": status})
    return sub


async def change_plan(
    session: AsyncSession,
    subscription: Subscription,
    new_plan: Plan,
    *,
    actor_id: str | None = None,
    user_id: str | None = None,
    reason: str = "",
    grant_credits: bool = True,
) -> Subscription:
    """Move a subscription to a new plan, recording history (§12) and starting a fresh
    monthly period."""
    old_slug = await _plan_slug(session, subscription.plan_id)
    if old_slug == new_plan.slug:
        return subscription
    now = utcnow()
    subscription.plan_id = new_plan.id
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.trial_status = TrialStatus.NONE
    subscription.trial_start = subscription.trial_end = None
    subscription.cancel_at_period_end = False
    subscription.current_period_start = now
    subscription.current_period_end = add_months(now, 1)
    await _record_history(
        session, organization_id=subscription.organization_id, old_plan=old_slug,
        new_plan=new_plan.slug, changed_by=actor_id, reason=reason or "plan change",
        user_id=user_id,
    )
    await session.flush()
    if grant_credits and new_plan.monthly_credits > 0:
        await credit_service.grant(
            session, subscription.organization_id, new_plan.monthly_credits,
            reason=f"Plan change to {new_plan.name}", reference_id=subscription.id,
            created_by=actor_id, user_id=user_id,
        )
    logger.info("subscription_plan_changed",
                extra={"organization_id": subscription.organization_id,
                       "old_plan": old_slug, "new_plan": new_plan.slug})
    return subscription


async def cancel(
    session: AsyncSession,
    subscription: Subscription,
    *,
    at_period_end: bool = True,
    actor_id: str | None = None,
) -> Subscription:
    if at_period_end:
        subscription.cancel_at_period_end = True
    else:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancel_at_period_end = False
    await session.flush()
    logger.info("subscription_cancelled",
                extra={"organization_id": subscription.organization_id,
                       "at_period_end": at_period_end})
    return subscription


async def set_status(
    session: AsyncSession, subscription: Subscription, status: str
) -> Subscription:
    subscription.status = status
    await session.flush()
    return subscription


async def get_or_404(session: AsyncSession, subscription_id: str) -> Subscription:
    sub = await get_subscription(session, subscription_id)
    if sub is None:
        raise NotFoundError("Subscription not found.", code="subscription_not_found")
    return sub


async def rollover(session: AsyncSession, subscription: Subscription) -> dict:
    """Advance a subscription whose period has ended (called by the maintenance loop).

    Returns a summary describing what changed so the caller can generate an invoice for
    the period that just closed. Does not delete any history."""
    now = utcnow()
    end = ensure_aware(subscription.current_period_end)
    result = {"rolled": False, "new_period": False, "credits_granted": 0,
              "closed_period_start": None, "closed_period_end": None, "status": subscription.status}
    if end is None or end > now:
        return result

    closed_start = ensure_aware(subscription.current_period_start)
    result["closed_period_start"] = closed_start
    result["closed_period_end"] = end

    # Trial ended → convert to a normal active period.
    if subscription.status == SubscriptionStatus.TRIALING:
        subscription.trial_status = TrialStatus.CONVERTED

    if subscription.cancel_at_period_end:
        subscription.status = SubscriptionStatus.CANCELLED
        result.update(rolled=True, status=subscription.status)
        await session.flush()
        return result

    # Open the next period.
    subscription.current_period_start = end
    subscription.current_period_end = add_months(end, 1)
    subscription.status = SubscriptionStatus.ACTIVE
    result.update(rolled=True, new_period=True, status=SubscriptionStatus.ACTIVE)

    plan = await session.get(Plan, subscription.plan_id)
    if plan is not None and plan.monthly_credits > 0:
        await credit_service.grant(
            session, subscription.organization_id, plan.monthly_credits,
            reason=f"Monthly credits for {plan.name} plan", reference_id=subscription.id,
        )
        result["credits_granted"] = plan.monthly_credits
    await session.flush()
    logger.info("subscription_rolled_over",
                extra={"organization_id": subscription.organization_id, "plan": plan.slug if plan else None})
    return result


async def expire_trials(session: AsyncSession) -> int:
    """Mark trials whose trial_end has passed as expired (maintenance sweep)."""
    now = utcnow()
    subs = (
        await session.execute(
            select(Subscription).where(Subscription.status == SubscriptionStatus.TRIALING)
        )
    ).scalars().all()
    count = 0
    for sub in subs:
        tend = ensure_aware(sub.trial_end)
        if tend is not None and tend <= now:
            sub.trial_status = TrialStatus.EXPIRED
            sub.status = SubscriptionStatus.EXPIRED
            count += 1
    if count:
        await session.flush()
    return count


async def list_subscriptions(
    session: AsyncSession,
    *,
    organization_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Subscription], int]:
    """Paginated subscriptions for the admin control plane (§31)."""
    conditions = []
    if organization_id:
        conditions.append(Subscription.organization_id == organization_id)
    if status:
        conditions.append(Subscription.status == status)

    base = select(Subscription)
    count_q = select(func.count()).select_from(Subscription)
    for cond in conditions:
        base = base.where(cond)
        count_q = count_q.where(cond)

    total = (await session.execute(count_q)).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Subscription.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), int(total)


async def plan_history(
    session: AsyncSession, organization_id: str, *, limit: int = 50, offset: int = 0
) -> tuple[list[PlanHistory], int]:
    """Append-only plan-change history for an organization (§12)."""
    count_q = (
        select(func.count())
        .select_from(PlanHistory)
        .where(PlanHistory.organization_id == organization_id)
    )
    total = (await session.execute(count_q)).scalar_one()
    rows = (
        await session.execute(
            select(PlanHistory)
            .where(PlanHistory.organization_id == organization_id)
            .order_by(PlanHistory.ts.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), int(total)
