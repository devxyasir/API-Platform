"""Admin overview & platform analytics (§35-37).

Read-only reporting for the admin console landing page: platform totals, an estimated
monthly recurring revenue and credit liability, plan distribution, new-account growth,
and the open security/risk queue depth. All figures come from real data (§62) — no
placeholders."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.models.enums import RiskStatus, SecurityEventStatus, SubscriptionStatus, UserStatus
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.security import RiskEvent, SecurityEvent
from app.models.subscription import Subscription
from app.models.user import User
from app.services import usage_service
from app.utils.time import day_start, utcnow

router = APIRouter(tags=["Overview"], prefix="/overview")

# Subscription states that represent live, revenue-bearing (or soon-to-bill) accounts.
_LIVE_STATUSES = (
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.PAST_DUE,
)


async def _count(session: AsyncSession, model, *conds) -> int:
    return int((await session.execute(select(func.count()).select_from(model).where(*conds))).scalar() or 0)


@router.get("", summary="Platform overview")
async def overview(
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    now = utcnow()
    since_30d = now - timedelta(days=30)

    total_users = await _count(session, User)
    active_users = await _count(session, User, User.status == UserStatus.ACTIVE)
    total_orgs = await _count(session, Organization)
    active_subs = await _count(
        session, Subscription, Subscription.status.in_(list(_LIVE_STATUSES))
    )

    # Estimated MRR: sum of monthly plan price over live, non-trial subscriptions.
    mrr = float(
        (
            await session.execute(
                select(func.coalesce(func.sum(Plan.price_monthly_usd), 0.0))
                .select_from(Subscription)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.status == SubscriptionStatus.ACTIVE)
            )
        ).scalar()
        or 0.0
    )

    # Outstanding credit liability across all organizations (cached mirror of the ledger).
    credit_liability = int(
        (await session.execute(select(func.coalesce(func.sum(Organization.credit_balance), 0)))).scalar() or 0
    )

    usage_30d = await usage_service.summary(session, since=since_30d, until=now)

    open_security = await _count(
        session, SecurityEvent, SecurityEvent.status == SecurityEventStatus.OPEN
    )
    open_risk = await _count(session, RiskEvent, RiskEvent.status == RiskStatus.OPEN)

    return {
        "users": {"total": total_users, "active": active_users},
        "organizations": {"total": total_orgs},
        "subscriptions": {"active": active_subs},
        "revenue": {"estimated_mrr_usd": round(mrr, 2), "credit_liability": credit_liability},
        "usage_30d": usage_30d,
        "queues": {"open_security_events": open_security, "open_risk_events": open_risk},
    }


@router.get("/plan-distribution", summary="Subscriptions per plan (§37)")
async def plan_distribution(
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Plan.slug, Plan.name, func.count(Subscription.id))
            .select_from(Plan)
            .outerjoin(
                Subscription,
                (Subscription.plan_id == Plan.id)
                & (Subscription.status.in_(list(_LIVE_STATUSES))),
            )
            .group_by(Plan.id, Plan.slug, Plan.name, Plan.sort_order)
            .order_by(Plan.sort_order, Plan.name)
        )
    ).all()
    return [
        {"plan_slug": slug, "plan_name": name, "subscriptions": int(count or 0)}
        for slug, name, count in rows
    ]


@router.get("/growth", summary="New accounts per day (§36)")
async def growth(
    days: int = Query(default=30, ge=1, le=365),
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    since = day_start() - timedelta(days=days - 1)
    rows = (
        await session.execute(
            select(User.created_at).where(User.created_at >= since).order_by(User.created_at)
        )
    ).all()
    # Bucket by UTC calendar day in Python (portable across SQLite/Postgres date functions).
    buckets: dict[str, int] = {}
    for (created_at,) in rows:
        key = created_at.date().isoformat()
        buckets[key] = buckets.get(key, 0) + 1
    series = [{"date": d, "new_users": n} for d, n in sorted(buckets.items())]
    return {"since": since, "days": days, "series": series, "total_new": sum(buckets.values())}
