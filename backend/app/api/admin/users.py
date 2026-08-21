"""Admin user management (§20-22, §44).

Uses granular RBAC (``require_permission``) rather than the legacy boolean admin check,
so a ``support``/``moderator`` admin role can act on accounts without holding every
permission. Covers the account list/detail views and the lifecycle actions (suspend,
disable, restrict, credit grant, quota reset, revoke keys, assign admin role)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import service as analytics
from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError, NotFoundError
from app.models.api_key import ApiKey
from app.models.enums import AdminRole, KeyStatus, UserStatus
from app.models.plan import Plan
from app.models.project import Project
from app.models.user import User
from app.schemas.admin import (
    AdminRoleUpdate,
    CreditGrant,
    QuotaResetIn,
    ReasonIn,
    SubscriptionOut,
    UserDetailOut,
)
from app.schemas.auth import UserCreateAdmin, UserOut, UserUpdateAdmin
from app.schemas.common import OK, Page
from app.services import (
    admin_service,
    api_key_service,
    audit_service,
    credit_service,
    organization_service,
    quota_service,
    subscription_service,
    user_service,
)

router = APIRouter(tags=["Users"], prefix="/users")

_VALID_ADMIN_ROLES = {r.value for r in AdminRole}


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("", response_model=Page[UserOut], summary="List users")
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
):
    users, total = await user_service.list_users(session, limit=limit, offset=offset)
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in users], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=UserOut, status_code=201, summary="Create a user")
async def create_user(
    body: UserCreateAdmin,
    request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await user_service.create_user(
        session, email=body.email, password=body.password, name=body.name,
        role=body.role, plan=body.plan, email_verified=True,
    )
    # Provision the account (personal org + subscription + opening credits) so a new
    # user is immediately usable and has an org to hold quota/credits (§4, §14, §31).
    await organization_service.provision_account(
        session, user, plan_slug=body.plan, actor_id=admin.id
    )
    await audit_service.record_audit(
        session, action="user.created", actor_id=admin.id, actor_email=admin.email,
        target_type="user", target_id=user.id, ip_hash=_ip(request),
    )
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut, summary="Get a user")
async def get_user(
    user_id: str,
    _admin: User = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
):
    user = await user_service.get_user_or_404(session, user_id)
    return UserOut.model_validate(user)


@router.get("/{user_id}/detail", response_model=UserDetailOut, summary="Aggregated account detail")
async def user_detail(
    user_id: str,
    _admin: User = Depends(require_permission("users.read")),
    session: AsyncSession = Depends(get_session),
):
    """Everything the account-detail tabs need in one call (§21, §44): the user, their
    personal organization + subscription/plan, credit balance, quota status, 30-day
    usage, and resource counts."""
    user = await user_service.get_user_or_404(session, user_id)
    org = await organization_service.get_personal_org(session, user)

    org_out = None
    sub_out = None
    plan_slug = plan_name = None
    credit_balance = 0
    quota: dict = {}
    usage_30d: dict = {}

    if org is not None:
        from app.schemas.admin import OrganizationOut  # local: avoids a broad import at top
        org_out = OrganizationOut.model_validate(org)
        credit_balance = int(org.credit_balance)
        sub = await subscription_service.get_active_subscription(session, org.id)
        if sub is not None:
            sub_out = SubscriptionOut.model_validate(sub)
            plan = await session.get(Plan, sub.plan_id)
            if plan is not None:
                plan_slug = sub_out.plan_slug = plan.slug
                plan_name = sub_out.plan_name = plan.name
        plan_slug = plan_slug or user.plan
        quota = await quota_service.quota_status(
            session, organization_id=org.id, plan_slug=plan_slug or "free", user_id=user.id
        )
        usage_30d = await analytics.user_stats(session, user.id, days=30)

    projects_count = int(
        (await session.execute(
            select(func.count()).select_from(Project).where(Project.owner_id == user.id)
        )).scalar() or 0
    )
    api_keys_count = int(
        (await session.execute(
            select(func.count()).select_from(ApiKey).where(ApiKey.user_id == user.id)
        )).scalar() or 0
    )

    return UserDetailOut(
        user=UserOut.model_validate(user).model_dump(),
        organization=org_out,
        subscription=sub_out,
        plan_slug=plan_slug,
        plan_name=plan_name,
        credit_balance=credit_balance,
        quota=quota,
        usage_30d=usage_30d,
        projects_count=projects_count,
        api_keys_count=api_keys_count,
        effective_permissions=sorted(admin_service.effective_permissions(user)),
    )


@router.patch("/{user_id}", response_model=UserOut, summary="Update a user")
async def update_user(
    user_id: str,
    body: UserUpdateAdmin,
    request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await user_service.get_user_or_404(session, user_id)
    changes = body.model_dump(exclude_unset=True)
    # Guard against an admin locking themselves out of their own account.
    if user.id == admin.id:
        if changes.get("role") not in (None, user.role):
            raise InvalidRequestError("You cannot change your own role.", code="self_role_change")
        if changes.get("status") not in (None, user.status):
            raise InvalidRequestError("You cannot change your own status.", code="self_status_change")
    for key, value in changes.items():
        setattr(user, key, value)
    await session.flush()
    await audit_service.record_audit(
        session, action="user.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="user", target_id=user.id, meta={"changes": list(changes)}, ip_hash=_ip(request),
    )
    return UserOut.model_validate(user)


@router.delete("/{user_id}", response_model=OK, summary="Deactivate a user")
async def delete_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    if user_id == admin.id:
        raise InvalidRequestError("You cannot delete your own account.", code="self_delete")
    user = await user_service.get_user_or_404(session, user_id)
    user.status = UserStatus.DELETED  # soft delete: retain history but block access
    await session.flush()
    await audit_service.record_audit(
        session, action="user.deleted", actor_id=admin.id, actor_email=admin.email,
        target_type="user", target_id=user.id, ip_hash=_ip(request),
    )
    return OK(detail="User deactivated.")


# --- lifecycle actions (§22) -------------------------------------------------
async def _set_status(
    session: AsyncSession, request: Request, admin: User, user_id: str,
    *, status: str, action: str, reason: str, allow_self: bool = False,
) -> User:
    if user_id == admin.id and not allow_self:
        raise InvalidRequestError("You cannot change your own account status.", code="self_status_change")
    user = await user_service.get_user_or_404(session, user_id)
    user.status = status
    await session.flush()
    await audit_service.record_audit(
        session, action=action, actor_id=admin.id, actor_email=admin.email,
        target_type="user", target_id=user.id, meta={"status": status, "reason": reason},
        ip_hash=_ip(request),
    )
    return user


@router.post("/{user_id}/suspend", response_model=UserOut, summary="Suspend an account")
async def suspend_user(
    user_id: str, body: ReasonIn, request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await _set_status(session, request, admin, user_id,
                             status=UserStatus.SUSPENDED, action="user.suspended", reason=body.reason)
    return UserOut.model_validate(user)


@router.post("/{user_id}/unsuspend", response_model=UserOut, summary="Reactivate an account")
async def unsuspend_user(
    user_id: str, body: ReasonIn, request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await _set_status(session, request, admin, user_id,
                             status=UserStatus.ACTIVE, action="user.unsuspended",
                             reason=body.reason, allow_self=True)
    return UserOut.model_validate(user)


@router.post("/{user_id}/disable", response_model=UserOut, summary="Disable an account")
async def disable_user(
    user_id: str, body: ReasonIn, request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await _set_status(session, request, admin, user_id,
                             status=UserStatus.DISABLED, action="user.disabled", reason=body.reason)
    return UserOut.model_validate(user)


@router.post("/{user_id}/restrict", response_model=UserOut, summary="Restrict an account")
async def restrict_user(
    user_id: str, body: ReasonIn, request: Request,
    admin: User = Depends(require_permission("users.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await _set_status(session, request, admin, user_id,
                             status=UserStatus.RESTRICTED, action="user.restricted", reason=body.reason)
    return UserOut.model_validate(user)


@router.post("/{user_id}/credits", summary="Grant credits to the account's organization")
async def grant_user_credits(
    user_id: str, body: CreditGrant, request: Request,
    admin: User = Depends(require_permission("credits.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await user_service.get_user_or_404(session, user_id)
    org = await organization_service.get_personal_org(session, user)
    if org is None:
        org = await organization_service.create_personal_org(session, user)
    txn = await credit_service.grant(
        session, org.id, body.amount, reason=body.reason or "Admin grant",
        expires_at=body.expires_at, created_by=admin.id, user_id=user.id,
    )
    await audit_service.record_audit(
        session, action="credit.granted", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org.id,
        meta={"user_id": user.id, "amount": body.amount, "balance_after": txn.balance_after},
        ip_hash=_ip(request),
    )
    return {"organization_id": org.id, "amount": body.amount, "balance_after": txn.balance_after}


@router.post("/{user_id}/quota-reset", summary="Reset the account's usage quota (§53)")
async def reset_user_quota(
    user_id: str, body: QuotaResetIn, request: Request,
    admin: User = Depends(require_permission("limits.write")),
    session: AsyncSession = Depends(get_session),
):
    user = await user_service.get_user_or_404(session, user_id)
    org = await organization_service.get_personal_org(session, user)
    if org is None:
        raise NotFoundError("User has no organization to reset quota for.", code="organization_not_found")
    event = await quota_service.reset_quota(
        session, organization_id=org.id, user_id=user.id, metric=body.metric,
        period=body.period, reason=body.reason, reset_by=admin.id,
    )
    await audit_service.record_audit(
        session, action="quota.reset", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=org.id,
        meta={"user_id": user.id, "metric": body.metric, "period": body.period,
              "previous_usage": event.previous_usage}, ip_hash=_ip(request),
    )
    return {"organization_id": org.id, "metric": body.metric, "period": body.period,
            "previous_usage": event.previous_usage}


@router.post("/{user_id}/revoke-all-keys", summary="Revoke all of an account's API keys")
async def revoke_all_keys(
    user_id: str, request: Request,
    admin: User = Depends(require_permission("keys.write")),
    session: AsyncSession = Depends(get_session),
):
    await user_service.get_user_or_404(session, user_id)
    keys = await api_key_service.list_api_keys(session, user_id=user_id)
    revoked = 0
    for key in keys:
        if key.status == KeyStatus.ACTIVE:
            await api_key_service.revoke_api_key(session, key)
            revoked += 1
    await audit_service.record_audit(
        session, action="user.keys_revoked", actor_id=admin.id, actor_email=admin.email,
        target_type="user", target_id=user_id, meta={"revoked": revoked}, ip_hash=_ip(request),
    )
    return {"revoked": revoked}


@router.post("/{user_id}/admin-role", response_model=UserOut, summary="Assign platform-admin role (super-admin)")
async def set_admin_role(
    user_id: str, body: AdminRoleUpdate, request: Request,
    admin: User = Depends(require_permission("admin.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Assign or clear a user's platform-admin role and per-user permission overrides.
    Gated on ``admin.manage`` (super-admin only)."""
    if body.admin_role is not None and body.admin_role not in _VALID_ADMIN_ROLES:
        raise InvalidRequestError(
            f"Invalid admin role. Choose one of: {', '.join(sorted(_VALID_ADMIN_ROLES))}.",
            code="invalid_admin_role",
        )
    user = await user_service.get_user_or_404(session, user_id)
    if user.id == admin.id and body.admin_role != AdminRole.SUPER_ADMIN:
        raise InvalidRequestError(
            "You cannot demote your own super-admin role.", code="self_admin_demote"
        )
    user.admin_role = body.admin_role
    user.admin_permissions = admin_service.valid_permissions(body.admin_permissions)
    await session.flush()
    await audit_service.record_audit(
        session, action="user.admin_role_set", actor_id=admin.id, actor_email=admin.email,
        target_type="user", target_id=user.id,
        meta={"admin_role": body.admin_role, "permissions": user.admin_permissions},
        ip_hash=_ip(request),
    )
    return UserOut.model_validate(user)


@router.get("/{user_id}/stats", summary="Per-user usage statistics")
async def user_stats(
    user_id: str,
    days: int = Query(default=30, ge=1, le=365),
    _admin: User = Depends(require_permission("usage.read")),
    session: AsyncSession = Depends(get_session),
):
    await user_service.get_user_or_404(session, user_id)
    return await analytics.user_stats(session, user_id, days=days)
