"""Self-service profile & account dashboard (``/account``).

The caller's own identity, password and a compact home-dashboard summary (plan, credit
balance, quota and 30-day usage). Nothing here can touch another account.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.account.deps import get_account_org, resolve_plan_slug
from app.database import get_session
from app.dependencies import get_current_user
from app.models.api_key import ApiKey
from app.models.enums import KeyStatus
from app.models.organization import Organization
from app.models.project import Project
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, UserOut
from app.schemas.common import OK
from app.services import audit_service, quota_service, usage_service, user_service
from app.utils.time import utcnow

router = APIRouter(tags=["Account"], prefix="")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


class ProfileUpdate(BaseModel):
    """Fields a user may change about themselves. Deliberately narrow — role, plan,
    status, credits and admin fields are NOT self-editable (those are admin actions)."""

    name: str | None = Field(default=None, max_length=120)


@router.get("/me", response_model=UserOut, summary="Your profile")
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut, summary="Update your profile")
async def update_me(
    body: ProfileUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        user.name = changes["name"]
    await session.flush()
    await audit_service.record_audit(
        session, action="account.profile_updated", actor_id=user.id, actor_email=user.email,
        target_type="user", target_id=user.id, meta={"changes": list(changes)}, ip_hash=_ip(request),
    )
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=OK, summary="Change your password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await user_service.change_password(session, user, body.current_password, body.new_password)
    await audit_service.record_audit(
        session, action="account.password_changed", actor_id=user.id, actor_email=user.email,
        target_type="user", target_id=user.id, ip_hash=_ip(request),
    )
    return OK(detail="Password updated.")


@router.get("/overview", summary="Account dashboard summary")
async def overview(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    """Everything the account home page needs in one call: plan, credit balance, monthly
    token quota and a 30-day usage rollup, plus resource counts — all self-scoped."""
    plan_slug = await resolve_plan_slug(session, org=org, user=user)
    quota = await quota_service.quota_status(
        session, organization_id=org.id, plan_slug=plan_slug, user_id=user.id
    )
    usage_30d = await usage_service.summary(
        session, organization_id=org.id, since=utcnow() - timedelta(days=30)
    )
    api_keys_count = int(
        (await session.execute(
            select(func.count()).select_from(ApiKey).where(
                ApiKey.user_id == user.id, ApiKey.status == KeyStatus.ACTIVE,
                ApiKey.is_system.is_(False),
            )
        )).scalar() or 0
    )
    projects_count = int(
        (await session.execute(
            select(func.count()).select_from(Project).where(Project.owner_id == user.id)
        )).scalar() or 0
    )
    return {
        "user": UserOut.model_validate(user).model_dump(),
        "organization_id": org.id,
        "plan_slug": plan_slug,
        "credit_balance": int(org.credit_balance),
        "quota": quota,
        "usage_30d": usage_30d,
        "active_api_keys": api_keys_count,
        "projects_count": projects_count,
    }
