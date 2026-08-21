"""Project, model, conversation, rate-limit and provider schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- Projects ---------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    concurrency_limit: int | None = None
    monthly_token_quota: int | None = None
    allowed_models: list[str] | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    concurrency_limit: int | None = None
    monthly_token_quota: int | None = None
    allowed_models: list[str] | None = None
    archived: bool | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    owner_id: str
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    concurrency_limit: int | None = None
    monthly_token_quota: int | None = None
    allowed_models: list[str]
    archived: bool
    created_at: datetime


# --- Models -----------------------------------------------------------------
class ModelCreate(BaseModel):
    public_id: str
    display_name: str
    upstream_model: str
    provider: str = "openai"
    enabled: bool = True
    supports_streaming: bool = True
    context_window: int = 8192
    max_output_tokens: int | None = None
    aliases: list[str] = Field(default_factory=list)
    is_default: bool = False
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    description: str = ""


class ModelUpdate(BaseModel):
    display_name: str | None = None
    upstream_model: str | None = None
    enabled: bool | None = None
    supports_streaming: bool | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    aliases: list[str] | None = None
    is_default: bool | None = None
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    description: str | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    public_id: str
    display_name: str
    description: str
    provider: str
    upstream_model: str
    enabled: bool
    supports_streaming: bool
    context_window: int
    max_output_tokens: int | None = None
    aliases: list[str]
    is_default: bool
    input_price_per_1m: float
    output_price_per_1m: float


# --- Conversations ----------------------------------------------------------
class ConversationCreate(BaseModel):
    title: str = "New conversation"
    project_id: str | None = None
    model: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    tokens: int
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    user_id: str
    project_id: str | None = None
    model: str | None = None
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


# --- Rate limits ------------------------------------------------------------
class RateLimitConfigIn(BaseModel):
    scope_type: str = Field(..., description="global|plan|user|project|api_key|model")
    scope_id: str = ""
    rpm: int | None = None
    rph: int | None = None
    rpd: int | None = None
    tpm: int | None = None
    tpd: int | None = None
    concurrency: int | None = None


class RateLimitConfigOut(RateLimitConfigIn):
    model_config = ConfigDict(from_attributes=True)
    id: str


# --- Provider ---------------------------------------------------------------
class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    provider_type: str
    enabled: bool
    base_url: str
    auth_mode: str
    key_masked: str
    timeout: float
    max_retries: int
    model_mapping: dict
    last_status: str
    last_latency_ms: float | None = None
    last_checked_at: datetime | None = None


class ProviderUpdate(BaseModel):
    enabled: bool | None = None
    timeout: float | None = None
    max_retries: int | None = None
    model_mapping: dict | None = None


# --- Organizations ----------------------------------------------------------
class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    owner_id: str
    status: str
    is_personal: bool
    credit_balance: int
    created_at: datetime


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    owner_id: str = Field(..., description="User who owns the organization.")
    slug: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class OrgStatusUpdate(BaseModel):
    status: str = Field(..., description="active | suspended | restricted | deleted")
    reason: str = ""


class OrgMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    user_id: str
    role: str
    status: str
    joined_at: datetime


class OrgMemberAdd(BaseModel):
    user_id: str
    role: str = "developer"


class OrgMemberUpdate(BaseModel):
    role: str


# --- Plans ------------------------------------------------------------------
class PlanCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=60)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    price_monthly_usd: float = 0.0
    price_yearly_usd: float = 0.0
    monthly_credits: int = 0
    trial_days: int = 0
    sort_order: int = 0
    is_public: bool = True
    limits: dict[str, int | None] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price_monthly_usd: float | None = None
    price_yearly_usd: float | None = None
    monthly_credits: int | None = None
    trial_days: int | None = None
    sort_order: int | None = None
    is_public: bool | None = None
    active: bool | None = None
    limits: dict[str, int | None] | None = None
    features: dict[str, Any] | None = None
    models: list[str] | None = None


class PlanOut(BaseModel):
    """Plan with its structured limits/features/models folded in (built by the router
    from the plan_service maps — not a plain ORM projection)."""

    id: str
    slug: str
    name: str
    description: str
    active: bool
    archived: bool
    is_public: bool
    price_monthly_usd: float
    price_yearly_usd: float
    monthly_credits: int
    trial_days: int
    sort_order: int
    created_at: datetime
    limits: dict[str, int | None] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=list)


# --- Subscriptions ----------------------------------------------------------
class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    plan_id: str
    status: str
    provider: str
    current_period_start: datetime
    current_period_end: datetime | None = None
    cancel_at_period_end: bool
    trial_status: str
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    created_at: datetime
    # Filled by the router for convenience (not ORM columns).
    plan_slug: str | None = None
    plan_name: str | None = None


class SubscriptionCreate(BaseModel):
    organization_id: str
    plan_id: str
    trial: bool | None = None
    reason: str = "admin subscription"


class SubscriptionChangePlan(BaseModel):
    plan_id: str
    reason: str = ""
    grant_credits: bool = True


class SubscriptionStatusUpdate(BaseModel):
    status: str = Field(..., description="trialing|active|past_due|paused|cancelled|expired")


class SubscriptionCancel(BaseModel):
    at_period_end: bool = True


class PlanHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    user_id: str | None = None
    old_plan: str | None = None
    new_plan: str
    changed_by: str | None = None
    reason: str
    ts: datetime


# --- Credits ----------------------------------------------------------------
class CreditTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    user_id: str | None = None
    type: str
    amount: int
    balance_after: int
    reason: str
    reference_id: str | None = None
    expires_at: datetime | None = None
    created_by: str | None = None
    ts: datetime


class CreditBalanceOut(BaseModel):
    organization_id: str
    balance: int


class CreditGrant(BaseModel):
    amount: int = Field(..., gt=0, description="Positive number of credits to grant.")
    reason: str = ""
    type: str = "grant"  # grant | bonus | purchase
    expires_at: datetime | None = None


class CreditAdjust(BaseModel):
    delta: int = Field(..., description="Signed correction; must be non-zero.")
    reason: str = Field(..., min_length=1)


class CreditRefund(BaseModel):
    amount: int = Field(..., gt=0)
    reason: str = ""


# --- Invoices / billing -----------------------------------------------------
class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    subscription_id: str | None = None
    number: str
    status: str
    period_start: datetime
    period_end: datetime
    plan_fee_usd: float
    usage_usd: float
    credits_applied_usd: float
    total_usd: float
    line_items: list = Field(default_factory=list)
    issued_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime


class InvoiceGenerate(BaseModel):
    organization_id: str
    period_start: datetime
    period_end: datetime
    subscription_id: str | None = None
    plan_fee_usd: float = 0.0


# --- Security & risk events -------------------------------------------------
class SecurityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str | None = None
    organization_id: str | None = None
    type: str
    status: str
    severity: str
    ip_hash: str | None = None
    user_agent: str | None = None
    meta: dict = Field(default_factory=dict)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    ts: datetime


class SecurityEventResolve(BaseModel):
    status: str = Field(default="resolved", description="resolved | ignored | open")


class RiskEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str | None = None
    organization_id: str | None = None
    type: str
    severity: str
    score: float
    status: str
    detail: dict = Field(default_factory=dict)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    ts: datetime


class RiskEventReview(BaseModel):
    status: str = Field(default="reviewed", description="reviewed | dismissed | actioned | open")


# --- Limit overrides --------------------------------------------------------
class LimitOverrideCreate(BaseModel):
    scope_type: str = Field(..., description="global|plan|organization|user|project|api_key|model")
    scope_id: str = ""
    metric: str = Field(..., description="One of LIMIT_METRICS.")
    value: int | None = Field(default=None, description="None = unlimited for this metric.")
    expires_at: datetime | None = None
    reason: str = ""


class LimitOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    scope_type: str
    scope_id: str
    metric: str
    value: int | None = None
    expires_at: datetime | None = None
    reason: str
    created_by: str | None = None
    created_at: datetime


# --- Model prices -----------------------------------------------------------
class ModelPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    model_public_id: str
    input_price_per_1m: float
    output_price_per_1m: float
    effective_from: datetime
    effective_until: datetime | None = None
    created_by: str | None = None
    ts: datetime


class ModelPriceSet(BaseModel):
    input_price_per_1m: float = Field(..., ge=0)
    output_price_per_1m: float = Field(..., ge=0)


# --- User admin actions & detail --------------------------------------------
class ReasonIn(BaseModel):
    reason: str = ""


class QuotaResetIn(BaseModel):
    metric: str = "monthly_token_quota"
    period: str = "month"
    reason: str = ""


class AdminRoleUpdate(BaseModel):
    admin_role: str | None = Field(default=None, description="Null clears platform-admin role.")
    admin_permissions: list[str] = Field(default_factory=list)


class UserDetailOut(BaseModel):
    """Aggregated account view for the user-detail tabs (§21, §44)."""

    user: dict
    organization: OrganizationOut | None = None
    subscription: SubscriptionOut | None = None
    plan_slug: str | None = None
    plan_name: str | None = None
    credit_balance: int = 0
    quota: dict = Field(default_factory=dict)
    usage_30d: dict = Field(default_factory=dict)
    projects_count: int = 0
    api_keys_count: int = 0
    effective_permissions: list[str] = Field(default_factory=list)
