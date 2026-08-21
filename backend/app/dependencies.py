"""FastAPI dependencies: authentication contexts and request metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import jwt
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_token
from app.database import get_session
from app.errors import AuthenticationError, PermissionDeniedError
from app.models.api_key import ApiKey
from app.models.enums import KeyStatus, OrgStatus, UserStatus
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.project import Project
from app.models.user import User
from app.rate_limit.limiter import LimitSet
from app.services import admin_service, api_key_service, plan_service, subscription_service
from app.services.limits_resolver import resolve_limits
from app.utils.time import ensure_aware, utcnow

# --- Security schemes (surface "Authorize" buttons in Swagger) ---
bearer_scheme = HTTPBearer(auto_error=False, description="Dashboard JWT")
api_key_scheme = APIKeyHeader(
    name="Authorization", auto_error=False,
    description="API key as 'Bearer sk_live_...'",
)


@dataclass
class AuthContext:
    """Everything the chat pipeline needs about an authenticated API caller."""

    user: User
    api_key: ApiKey
    project: Project | None
    limits: LimitSet
    scopes: list[str] = field(default_factory=list)
    # Owning organization + resolved subscription plan (the entities that hold quota,
    # credits and model access). Populated by get_api_context; primitives only, so they
    # stay valid after the session commits (expire_on_commit=False).
    organization_id: str | None = None
    plan_id: str | None = None
    plan_slug: str = "free"

    def require_scope(self, scope: str) -> None:
        if scope not in self.scopes:
            raise PermissionDeniedError(
                f"This API key is missing the required scope '{scope}'.",
                code="insufficient_scope",
            )


def _extract_api_key(request: Request) -> str | None:
    """Pull the caller's API key from the request headers, as leniently as is safe.

    Accepts, in order of preference:
      * ``Authorization: Bearer <key>``  — OpenAI-style (what most SDKs/coding agents send)
      * ``Authorization: <key>``          — the raw key with no scheme, for tools that pass
        the key verbatim without wrapping it in ``Bearer``
      * ``x-api-key: <key>``              — Anthropic-style
      * ``api-key: <key>``                — Azure-style

    The value is looked up by hash regardless of prefix, so a stray scheme word never matters
    for a genuinely valid key.
    """
    auth = request.headers.get("authorization")
    if auth:
        token = auth.strip()
        # Split a leading scheme word: "Bearer <key>" -> "<key>". Anything else (incl. a raw
        # key with no scheme) is used verbatim. A bare "Bearer" with no key yields "".
        first, _, rest = token.partition(" ")
        if first.lower() == "bearer":
            token = rest.strip()
        if token:
            return token
    for header in ("x-api-key", "api-key"):
        val = request.headers.get(header)
        if val and val.strip():
            return val.strip()
    return None


async def _resolve_org_and_plan(
    session: AsyncSession, *, user: User, key: ApiKey
) -> tuple[str | None, str | None, str]:
    """Return ``(organization_id, plan_id, plan_slug)`` for an authenticated caller and
    enforce organization status (§29).

    The organization is the API key's org if set, else the user's personal org. The plan
    is the org's active subscription plan, falling back to the user's plan slug when the
    org has no subscription yet (or the user has no org). Only primitive ids/slug are
    returned so they remain valid after the session commits."""
    organization_id = key.organization_id or user.primary_org_id
    plan_slug = user.plan or "free"

    if organization_id:
        org = await session.get(Organization, organization_id)
        if org is not None:
            if org.status == OrgStatus.DELETED:
                raise AuthenticationError("Invalid API key.", code="invalid_api_key")
            if org.status == OrgStatus.SUSPENDED:
                raise PermissionDeniedError(
                    "This organization has been suspended.", code="organization_suspended"
                )
            if org.status == OrgStatus.RESTRICTED:
                raise PermissionDeniedError(
                    "This organization is restricted from making API requests.",
                    code="organization_restricted",
                )
            sub = await subscription_service.get_active_subscription(session, organization_id)
            if sub is not None:
                plan = await session.get(Plan, sub.plan_id)
                if plan is not None:
                    return organization_id, plan.id, plan.slug

    # No org / no active subscription → resolve the plan id from the user's slug.
    plan = await plan_service.get_plan_by_slug(session, plan_slug)
    return organization_id, (plan.id if plan is not None else None), plan_slug


async def get_api_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    raw = _extract_api_key(request)
    if not raw:
        raise AuthenticationError(
            "Missing API key. Send it in the 'Authorization' header (with or without a "
            "'Bearer ' prefix) or as 'x-api-key'.",
            code="missing_api_key",
        )

    key = await api_key_service.lookup_by_raw(session, raw)
    if key is None:
        raise AuthenticationError("Invalid API key.", code="invalid_api_key")

    return await build_context_for_key(session, key)


async def build_context_for_key(
    session: AsyncSession, key: ApiKey, *, touch_last_used: bool = True
) -> AuthContext:
    """Turn an already-resolved :class:`ApiKey` into an :class:`AuthContext`, applying the
    exact same key/user/organization enforcement as :func:`get_api_context`.

    Extracted so the first-party chat product (session-authed) can resolve its hidden
    per-user system key through *identical* checks and reuse the untouched chat pipeline —
    there is no second, drift-prone authorization path. ``get_api_context`` handles the raw
    key lookup and delegates the rest here."""
    now = utcnow()
    if key.status == KeyStatus.REVOKED:
        raise AuthenticationError("This API key has been revoked.", code="key_revoked")
    if key.status == KeyStatus.DISABLED:
        raise AuthenticationError("This API key has been disabled.", code="key_disabled")
    expires_at = ensure_aware(key.expires_at)
    if expires_at and expires_at <= now:
        if key.status != KeyStatus.EXPIRED:
            key.status = KeyStatus.EXPIRED
            await session.flush()
        raise AuthenticationError("This API key has expired.", code="key_expired")

    user = await session.get(User, key.user_id)
    if user is None or user.status == UserStatus.DELETED:
        raise AuthenticationError("Invalid API key.", code="invalid_api_key")
    if user.status == UserStatus.SUSPENDED:
        raise PermissionDeniedError("This account has been suspended.", code="account_suspended")
    if user.status == UserStatus.DISABLED:
        raise PermissionDeniedError("This account has been disabled.", code="account_disabled")
    if user.status == UserStatus.RESTRICTED:
        raise PermissionDeniedError(
            "This account is restricted from making API requests.", code="account_restricted"
        )
    if user.status == UserStatus.PENDING:
        raise PermissionDeniedError(
            "This account is pending activation.", code="account_pending"
        )

    # Resolve owning org + subscribed plan and enforce organization status (§29).
    organization_id, plan_id, plan_slug = await _resolve_org_and_plan(session, user=user, key=key)

    project = await session.get(Project, key.project_id) if key.project_id else None
    limits = await resolve_limits(session, user=user, api_key=key, project=project)

    # Update last-used at most once per minute to avoid a write on every request.
    # Commit immediately: otherwise this write holds an open transaction (and, on
    # SQLite, the single writer lock) for the whole request, which would deadlock
    # the fresh-session writes used by streaming / error / rate-limit accounting.
    if touch_last_used:
        last_used_at = ensure_aware(key.last_used_at)
        if last_used_at is None or (now - last_used_at) > timedelta(seconds=60):
            key.last_used_at = now
            await session.commit()

    return AuthContext(
        user=user, api_key=key, project=project, limits=limits,
        scopes=list(key.scopes or []),
        organization_id=organization_id, plan_id=plan_id, plan_slug=plan_slug,
    )


def require_scope(scope: str):
    async def _dep(ctx: AuthContext = Depends(get_api_context)) -> AuthContext:
        ctx.require_scope(scope)
        return ctx

    return _dep


# --- Dashboard (JWT) auth ----------------------------------------------------
async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> User:
    if creds is None or not creds.credentials:
        raise AuthenticationError("Not authenticated.", code="not_authenticated")
    try:
        payload = decode_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Session expired. Please log in again.", code="token_expired")
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid authentication token.", code="invalid_token")

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.", code="invalid_token")

    # Record the session scope (user|admin) so admin gates can require an admin session.
    request.state.token_scope = payload.get("scope", "user")

    user = await session.get(User, payload.get("sub", ""))
    if user is None or user.status == UserStatus.DELETED:
        raise AuthenticationError("User no longer exists.", code="invalid_token")
    if user.status == UserStatus.SUSPENDED:
        raise PermissionDeniedError("This account has been suspended.", code="account_suspended")
    return user


async def get_chat_context(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    """Auth context for the first-party chat product.

    The chat surface is authenticated by the dashboard JWT (like the rest of ``/account``),
    NOT by an API key. This dependency bridges that session to the shared chat pipeline: it
    resolves (provisioning on first use) the caller's hidden ``is_system`` API key and runs
    it through the exact same enforcement as a real ``/v1`` key. Chat-product gates
    (chat_enabled, public_chat allow-list, monthly_chat_messages) are applied by the chat
    router ABOVE ``chat_service.prepare`` so the ``/v1`` surface stays byte-identical."""
    key = await api_key_service.get_or_create_system_key(session, user.id)
    return await build_context_for_key(session, key)


def _ensure_admin_scope(request: Request) -> None:
    """The token must have been minted by the admin console (scope=admin). A normal
    user-scoped token is rejected from every admin surface even if the account holds an
    admin role — admin access requires logging in through the admin console."""
    if getattr(request.state, "token_scope", "user") != "admin":
        raise PermissionDeniedError(
            "Administrative access requires an admin console session.",
            code="admin_session_required",
        )


async def require_admin(request: Request, user: User = Depends(get_current_user)) -> User:
    _ensure_admin_scope(request)
    if not user.is_admin:
        raise PermissionDeniedError("Administrator privileges required.", code="admin_required")
    return user


async def require_platform_admin(request: Request, user: User = Depends(get_current_user)) -> User:
    """Any platform-admin standing (an ``admin_role`` or per-user override, or a legacy
    admin/owner), AND an admin-scoped session. Distinct from :func:`require_admin`, which
    also requires the legacy ``is_admin`` roles — RBAC roles such as ``support`` may keep
    ``role=developer``."""
    _ensure_admin_scope(request)
    if not admin_service.is_platform_admin(user):
        raise PermissionDeniedError("Administrator privileges required.", code="admin_required")
    return user


def require_permission(permission: str):
    """Dependency factory enforcing a single admin RBAC permission (§2).

    The caller must have an admin-scoped session AND platform-admin standing AND hold
    ``permission`` (through their role's grants or a per-user override). ``super_admin``/
    legacy ``admin`` hold every permission, so existing single-admin deployments keep
    working unchanged."""

    async def _dep(user: User = Depends(require_platform_admin)) -> User:
        if not admin_service.has_permission(user, permission):
            raise PermissionDeniedError(
                f"This action requires the '{permission}' permission.",
                code="insufficient_permission",
            )
        return user

    return _dep
