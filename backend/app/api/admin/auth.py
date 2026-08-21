"""Dashboard authentication: register, login, current user, change password.

Two token scopes are issued here:
- ``user``  — normal account login (/login, /register). Grants the self-service
  ``/account/*`` API only.
- ``admin`` — issued ONLY by /admin-login and ONLY to platform admins. Required by the
  ``/admin/*`` control plane. A user-scoped token can never reach admin endpoints even
  if the account later gains an admin role, so admin access is possible only by logging
  in through the admin console. (§2, separation of admin from normal login.)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import envelope
from app.auth.security import create_access_token
from app.config import settings
from app.database import get_session
from app.dependencies import get_current_user
from app.errors import PermissionDeniedError
from app.models.enums import AdminRole, PlanSlug, UserRole
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import OK
from app.services import admin_service, audit_service, organization_service, user_service

router = APIRouter(tags=["Authentication"], prefix="/auth")


def _issue_token(user: User, *, scope: str = "user") -> TokenResponse:
    token = create_access_token(
        user.id, extra={"role": user.role, "email": user.email, "scope": scope}
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        scope=scope,
        enc_key=envelope.client_key_b64(user.id) if settings.payload_encryption_enabled else None,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=201, summary="Register a new account")
async def register(body: RegisterRequest, request: Request, session: AsyncSession = Depends(get_session)):
    # The very first user becomes the administrator/owner of this deployment.
    first_user = (await user_service.count_users(session)) == 0
    role = UserRole.ADMIN if first_user else UserRole.DEVELOPER
    plan = PlanSlug.ENTERPRISE if first_user else PlanSlug.FREE
    user = await user_service.create_user(
        session, email=body.email, password=body.password, name=body.name,
        role=role, plan=plan, email_verified=first_user,
    )
    # The first user is the platform super-admin (can manage other admins' RBAC roles).
    if first_user:
        user.admin_role = AdminRole.SUPER_ADMIN
        await session.flush()
    # Provision the account: personal org + subscription + opening credits (§4, §14, §31).
    await organization_service.provision_account(
        session, user, plan_slug=plan, actor_id=user.id
    )
    await audit_service.record_audit(
        session, action="user.registered", actor_id=user.id, actor_email=user.email,
        target_type="user", target_id=user.id, ip_hash=getattr(request.state, "ip_hash", None),
    )
    # Registration always yields a user-scoped session, even for the first (admin) user;
    # they obtain an admin session by logging in through the admin console.
    return _issue_token(user, scope="user")


@router.post("/login", response_model=TokenResponse, summary="Log in (normal account)")
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    user = await user_service.authenticate(session, body.email, body.password)
    await audit_service.record_audit(
        session, action="account.login", actor_id=user.id, actor_email=user.email,
        ip_hash=getattr(request.state, "ip_hash", None),
    )
    return _issue_token(user, scope="user")


@router.post("/admin-login", response_model=TokenResponse, summary="Log in to the admin console")
async def admin_login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    """Authenticate a platform admin and mint an ``admin``-scoped session.

    Non-admins are rejected here with the same generic message as a bad password, so this
    endpoint does not reveal which accounts hold admin rights."""
    user = await user_service.authenticate(session, body.email, body.password)
    if not admin_service.is_platform_admin(user):
        # Deliberately identical to an auth failure — don't disclose admin membership.
        await audit_service.record_audit(
            session, action="admin.login_denied", actor_id=user.id, actor_email=user.email,
            ip_hash=getattr(request.state, "ip_hash", None),
        )
        raise PermissionDeniedError("Invalid credentials.", code="invalid_credentials")
    await audit_service.record_audit(
        session, action="admin.login", actor_id=user.id, actor_email=user.email,
        ip_hash=getattr(request.state, "ip_hash", None),
    )
    return _issue_token(user, scope="admin")


@router.post("/logout", response_model=OK, summary="Log out")
async def logout(user: User = Depends(get_current_user)):
    # Stateless JWTs — the client discards the token. (Add a denylist here if needed.)
    return OK(detail="Logged out.")


@router.get("/me", response_model=UserOut, summary="Current user")
async def me(user: User = Depends(get_current_user)):
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
        session, action="password.changed", actor_id=user.id, actor_email=user.email,
        target_type="user", target_id=user.id, ip_hash=getattr(request.state, "ip_hash", None),
    )
    return OK(detail="Password updated.")
