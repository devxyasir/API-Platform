"""Shared dependencies for the self-service account API.

``get_account_org`` resolves the caller's personal organization — the entity that owns
their quota, credits, subscription, invoices and usage. FastAPI caches dependencies per
request, so an endpoint may depend on both ``get_current_user`` and ``get_account_org``
without authenticating twice.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import get_current_user
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.user import User
from app.services import organization_service, subscription_service


async def get_account_org(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Organization:
    """The caller's personal organization.

    Registration provisions this up front; it is created lazily here only for legacy
    accounts that predate account provisioning. ``create_personal_org`` is idempotent, so
    a concurrent read never produces a duplicate."""
    org = await organization_service.get_personal_org(session, user)
    if org is None:
        org = await organization_service.create_personal_org(session, user)
    return org


async def resolve_plan_slug(
    session: AsyncSession, *, org: Organization, user: User
) -> str:
    """The plan slug in effect for the caller: the org's active subscription plan, falling
    back to the user's coarse plan field (then ``free``)."""
    sub = await subscription_service.get_active_subscription(session, org.id)
    if sub is not None:
        plan = await session.get(Plan, sub.plan_id)
        if plan is not None:
            return plan.slug
    return user.plan or "free"
