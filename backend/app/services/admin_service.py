"""Granular admin RBAC (§2).

Platform administration is governed by an :class:`AdminRole` (a coarse role with a
default grant set) plus an optional per-user ``admin_permissions`` override list that
is unioned on top. Permissions are dot-namespaced strings (``"billing.write"``); a
grant may also be the wildcard ``"*"`` (all) or a namespace wildcard (``"billing.*"``).

RBAC lives in code (not the DB) so the permission model is reviewable and versioned.
The DB only stores which role a user holds and any per-user overrides.
"""
from __future__ import annotations

from app.models.enums import AdminRole, UserRole
from app.models.user import User

# --- Canonical permission catalogue -----------------------------------------
# (resource.action). Keep in sync with the admin routers' require_permission calls.
ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        "users.read", "users.write",
        "orgs.read", "orgs.write",
        "projects.read", "projects.write",
        "plans.read", "plans.write",
        "subscriptions.read", "subscriptions.write",
        "credits.read", "credits.write",
        "billing.read", "billing.write",
        "usage.read",
        "keys.read", "keys.write",
        "models.read", "models.write",
        "limits.read", "limits.write",
        "security.read", "security.write",
        "risk.read", "risk.write",
        "audit.read",
        "system.read", "system.write",
        "admin.manage",  # manage other admins / assign RBAC roles (super-admin only)
    }
)

WILDCARD = "*"

# Raw grants per role. "*" = every permission; "<ns>.*" = every permission in a
# namespace. Expanded to concrete permissions by :func:`_expand`.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    AdminRole.SUPER_ADMIN: frozenset({WILDCARD}),
    # Full operator, but cannot manage other admins' RBAC roles.
    AdminRole.ADMIN: frozenset(ALL_PERMISSIONS - {"admin.manage"}),
    # Customer support: read broadly, act on accounts/keys, but never billing/system.
    AdminRole.SUPPORT: frozenset(
        {
            "users.read", "users.write",
            "orgs.read", "projects.read",
            "plans.read", "subscriptions.read", "credits.read", "billing.read",
            "usage.read",
            "keys.read", "keys.write",
            "models.read",
            "limits.read",
            "security.read", "risk.read",
            "audit.read",
        }
    ),
    # Billing operator: plans/subscriptions/credits/invoices, but never system config.
    AdminRole.BILLING_ADMIN: frozenset(
        {
            "users.read",
            "orgs.read",
            "plans.read", "plans.write",
            "subscriptions.read", "subscriptions.write",
            "credits.read", "credits.write",
            "billing.read", "billing.write",
            "usage.read",
            "audit.read",
        }
    ),
    # Read-only analytics/reporting.
    AdminRole.ANALYST: frozenset(
        {
            "users.read", "orgs.read", "projects.read",
            "plans.read", "subscriptions.read", "credits.read", "billing.read",
            "usage.read",
            "keys.read", "models.read", "limits.read",
            "security.read", "risk.read", "audit.read",
            "system.read",
        }
    ),
    # Trust & safety: abuse handling on accounts/keys + security/risk queues.
    AdminRole.MODERATOR: frozenset(
        {
            "users.read", "users.write",
            "orgs.read", "projects.read",
            "usage.read",
            "keys.read", "keys.write",
            "security.read", "security.write",
            "risk.read", "risk.write",
            "audit.read",
        }
    ),
}


def _expand(grants: frozenset[str]) -> set[str]:
    """Resolve wildcard grants to a concrete permission set."""
    if WILDCARD in grants:
        return set(ALL_PERMISSIONS)
    resolved: set[str] = set()
    for g in grants:
        if g == WILDCARD:
            return set(ALL_PERMISSIONS)
        if g.endswith(".*"):
            ns = g[:-2]
            resolved.update(p for p in ALL_PERMISSIONS if p.startswith(ns + "."))
        elif g in ALL_PERMISSIONS:
            resolved.add(g)
    return resolved


def role_permissions(admin_role: str | None) -> set[str]:
    """Concrete permissions granted by an admin role alone (no per-user overrides)."""
    if not admin_role:
        return set()
    return _expand(ROLE_PERMISSIONS.get(admin_role, frozenset()))


def _resolved_role(user: User) -> str | None:
    """The effective admin role for a user.

    Legacy admins (``role`` in {admin, owner}) with no explicit ``admin_role`` are
    treated as full ADMIN so the pre-RBAC ``is_admin`` contract keeps working.
    """
    if user.admin_role:
        return user.admin_role
    if user.role in (UserRole.ADMIN, UserRole.OWNER):
        return AdminRole.ADMIN
    return None


def effective_permissions(user: User) -> set[str]:
    """Concrete permission set for a user: role grants ∪ per-user overrides."""
    perms = role_permissions(_resolved_role(user))
    overrides = user.admin_permissions or []
    if isinstance(overrides, list):
        perms |= _expand(frozenset(str(p) for p in overrides))
    return perms


def is_platform_admin(user: User) -> bool:
    """True if the user has any admin standing at all (role or overrides)."""
    return _resolved_role(user) is not None or bool(user.admin_permissions)


def has_permission(user: User, permission: str) -> bool:
    return permission in effective_permissions(user)


def valid_permissions(permissions: list[str]) -> list[str]:
    """Filter an override list down to recognized permissions (drops unknowns)."""
    return [p for p in permissions if p == WILDCARD or p.endswith(".*") or p in ALL_PERMISSIONS]
