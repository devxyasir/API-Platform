"""Import all models so their mappers register with the shared metadata."""
from app.models.api_key import ApiKey
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.billing import Invoice
from app.models.conversation import Conversation, Message
from app.models.credit import CreditTransaction
from app.models.governance import LimitOverride, QuotaResetEvent
from app.models.memory import Embedding, UserMemory
from app.models.model import Model
from app.models.organization import Organization, OrganizationMember
from app.models.plan import Plan, PlanFeature, PlanLimit, PlanModel
from app.models.pricing import ModelPrice
from app.models.project import Project
from app.models.provider_config import ProviderConfig
from app.models.rate_limit import RateLimitConfig, RateLimitEvent
from app.models.request_log import RequestLog
from app.models.security import RiskEvent, SecurityEvent
from app.models.subscription import PlanHistory, Subscription
from app.models.usage import UsageAggregate, UsageRecord
from app.models.user import User
from app.models.user_settings import UserSettings

__all__ = [
    "Base",
    "User",
    "ApiKey",
    "Project",
    "Model",
    "Conversation",
    "Message",
    "RequestLog",
    "UsageRecord",
    "UsageAggregate",
    "RateLimitConfig",
    "RateLimitEvent",
    "AuditLog",
    "ProviderConfig",
    # Enterprise admin / account-management module
    "Organization",
    "OrganizationMember",
    "Plan",
    "PlanLimit",
    "PlanFeature",
    "PlanModel",
    "Subscription",
    "PlanHistory",
    "CreditTransaction",
    "Invoice",
    "SecurityEvent",
    "RiskEvent",
    "LimitOverride",
    "QuotaResetEvent",
    "ModelPrice",
    # First-party chat product
    "UserSettings",
    "UserMemory",
    "Embedding",
]
