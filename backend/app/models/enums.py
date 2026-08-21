"""Enum-like string constants shared across models (stored as plain strings for
SQLite/Postgres portability).

These are ``StrEnum``s so ``UserStatus.ACTIVE == "active"`` holds and the values
serialize transparently to JSON and SQL. Plans themselves now live in the database
(see :mod:`app.models.plan`); :class:`PlanSlug` only enumerates the *well-known*
default slugs the bootstrap seeds and the code references by name.
"""
from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Dashboard / ownership role (distinct from :class:`AdminRole` RBAC)."""

    ADMIN = "admin"
    OWNER = "owner"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class UserStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"        # awaiting email verification / approval
    SUSPENDED = "suspended"    # temporarily blocked (recoverable)
    RESTRICTED = "restricted"  # limited access (e.g. read-only, no new usage)
    DISABLED = "disabled"      # administratively turned off
    DELETED = "deleted"        # soft-deleted


class AccountType(StrEnum):
    """Coarse account classification (§5). Independent of the subscribed plan."""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"
    STAFF = "staff"
    ADMIN = "admin"


class PlanSlug(StrEnum):
    """Well-known default plan slugs seeded by bootstrap. Plans are DB rows now —
    this only documents/references the built-in ones."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    TEAM = "team"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class KeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    DISABLED = "disabled"  # disabled alongside its owner/org (recoverable)


class OrgStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RESTRICTED = "restricted"
    DELETED = "deleted"


class OrgRole(StrEnum):
    """A user's role *within* an organization."""

    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    BILLING = "billing"
    VIEWER = "viewer"


class MemberStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    REMOVED = "removed"


class AdminRole(StrEnum):
    """Platform administration role driving granular RBAC (§2)."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPPORT = "support"
    BILLING_ADMIN = "billing_admin"
    ANALYST = "analyst"
    MODERATOR = "moderator"


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TrialStatus(StrEnum):
    NONE = "none"
    ACTIVE = "active"
    CONVERTED = "converted"
    EXPIRED = "expired"


class CreditTxnType(StrEnum):
    """Credit ledger entry kinds (§14). ``amount`` sign follows the type:
    grants/refunds/purchases/bonuses/adjustments may be positive; usage and
    expiration are negative."""

    GRANT = "grant"
    USAGE = "usage"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"
    EXPIRATION = "expiration"
    PURCHASE = "purchase"
    BONUS = "bonus"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class QuotaPeriod(StrEnum):
    DAY = "day"
    MONTH = "month"


class AggregateGranularity(StrEnum):
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventType(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    ACCOUNT_LOCKED = "account_locked"
    PASSWORD_CHANGED = "password_changed"
    KEY_CREATED = "api_key_created"
    KEY_REVOKED = "api_key_revoked"
    SUSPICIOUS_LOGIN = "suspicious_login"
    PERMISSION_DENIED = "permission_denied"


class SecurityEventStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class RiskEventType(StrEnum):
    USAGE_SPIKE = "usage_spike"
    RAPID_KEY_CREATION = "rapid_key_creation"
    QUOTA_ABUSE = "quota_abuse"
    REPEATED_FAILED_LOGINS = "repeated_failed_logins"
    CREDIT_BURN = "credit_burn"


class RiskStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"


class TokenCountSource(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    TOKENIZER_ESTIMATED = "tokenizer_estimated"


class RequestStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


# Canonical limit/quota metric names used by plan_limits, limit_overrides, and the
# limits resolver. The first six mirror the rate-limiter dimensions; the remaining
# ones are longer-window quotas enforced as real pre-flight checks. ``monthly_chat_messages``
# caps first-party chat-product turns (counted from the hidden per-user system key's
# success usage rows) and is NOT a rate-limiter dimension.
LIMIT_METRICS = frozenset(
    {
        "rpm",
        "rph",
        "rpd",
        "tpm",
        "tpd",
        "concurrency",
        "monthly_token_quota",
        "daily_token_quota",
        "monthly_chat_messages",
    }
)

# Scope levels for limit overrides / rate-limit configs.
LIMIT_SCOPES = frozenset({"global", "plan", "organization", "user", "project", "api_key", "model"})


# Available API-key scopes (consumer-facing, NOT admin permissions).
SCOPES = frozenset(
    {
        "chat:write",
        "chat:read",
        "models:read",
        "usage:read",
        "conversations:write",
        "conversations:read",
    }
)
DEFAULT_SCOPES = ["chat:write", "chat:read", "models:read", "usage:read"]
