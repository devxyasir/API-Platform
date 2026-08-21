"""First-run bootstrap: seed default models, the provider config, and an admin user."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging_config import get_logger
from app.models.enums import AdminRole, UserRole
from app.models.model import Model
from app.models.plan import Plan, PlanFeature, PlanLimit, PlanModel
from app.models.pricing import ModelPrice
from app.models.provider_config import ProviderConfig
from app.models.user import User
from app.services import organization_service, user_service

logger = get_logger("app.bootstrap")

# Sensible defaults for an OpenAI upstream. Aliases keep customer code stable if
# the underlying model changes (e.g. "fast" can be repointed without breaking apps).
DEFAULT_MODELS = [
    {
        "public_id": "gpt-4o", "display_name": "GPT-4o", "provider": "openai",
        "upstream_model": "gpt-4o",
        "aliases": ["default", "smart", "C"], "is_default": True, "context_window": 128000,
        "input_price_per_1m": 2.5, "output_price_per_1m": 10.0,
        "public_chat": True, "supports_vision": True,
        "description": "Most capable general-purpose model.",
    },
    {
        "public_id": "gpt-4o-mini", "display_name": "GPT-4o mini", "provider": "openai",
        "upstream_model": "gpt-4o-mini",
        "aliases": ["fast", "balanced"], "context_window": 128000,
        "input_price_per_1m": 0.15, "output_price_per_1m": 0.6,
        "public_chat": True, "supports_vision": True,
        "description": "Fast, low-cost model for everyday tasks.",
    },
    {
        "public_id": "gpt-3.5-turbo", "display_name": "GPT-3.5 Turbo", "provider": "openai",
        "upstream_model": "gpt-3.5-turbo",
        "aliases": [], "context_window": 16385,
        "input_price_per_1m": 0.5, "output_price_per_1m": 1.5,
        "description": "Legacy fast model.",
    },
    {
        # Kept reachable on /v1 for the deployment owner, but deliberately NOT offered in
        # the public chat product (public_chat stays False): the shared trace showed this
        # keyless upstream being used to work around AI-safety refusals, so it is not wired
        # into a multi-user chat surface. An admin can still flip the flag explicitly.
        "public_id": "notrack-c", "display_name": "Notrack C", "provider": "notrack",
        "upstream_model": "C",
        "aliases": ["notrack"], "context_window": 262144,
        "input_price_per_1m": 0.0, "output_price_per_1m": 0.0,
        "public_chat": False, "supports_vision": False,
        "description": "Anonymous debate model served by notrack.ai (keyless).",
    },
]


# Default subscription plans. Limits are the *effective* ceilings the resolver reads
# from the DB (falling back to the hard-coded PLAN_LIMITS only when a plan/metric row is
# missing). A metric omitted here means "unlimited" (no row is created) — that is how
# enterprise/custom stay uncapped. Credits, token quota, and money are kept as SEPARATE
# concepts (§58): `monthly_credits` is a prepaid grant, `monthly_token_quota` is a usage
# ceiling, `price_monthly_usd` is money. `models=[]` means every enabled model is allowed;
# a non-empty list restricts the plan to exactly those public ids (§55).
DEFAULT_PLANS = [
    {
        "slug": "free", "name": "Free", "sort_order": 10,
        "description": "Personal experimentation with low-cost models.",
        "price_monthly_usd": 0.0, "price_yearly_usd": 0.0, "monthly_credits": 0, "trial_days": 0,
        "limits": {"rpm": 20, "rph": 300, "rpd": 10_000, "tpm": 40_000, "tpd": 100_000,
                   "concurrency": 3, "monthly_token_quota": 1_000_000, "monthly_chat_messages": 200},
        "features": {"support": "community", "analytics_retention_days": 7,
                     "byok": False, "priority_routing": False, "sla": None, "chat_enabled": True},
        "models": ["gpt-4o-mini", "gpt-3.5-turbo", "notrack-c"],
    },
    {
        "slug": "starter", "name": "Starter", "sort_order": 20,
        "description": "For individuals shipping small applications.",
        "price_monthly_usd": 20.0, "price_yearly_usd": 200.0, "monthly_credits": 5_000, "trial_days": 0,
        "limits": {"rpm": 60, "rph": 1_500, "rpd": 50_000, "tpm": 100_000, "tpd": 1_000_000,
                   "concurrency": 5, "monthly_token_quota": 20_000_000, "monthly_chat_messages": 2_000},
        "features": {"support": "email", "analytics_retention_days": 30,
                     "byok": False, "priority_routing": False, "sla": None, "chat_enabled": True},
        "models": [],
    },
    {
        "slug": "pro", "name": "Pro", "sort_order": 30,
        "description": "Production workloads with full model access.",
        "price_monthly_usd": 100.0, "price_yearly_usd": 1_000.0, "monthly_credits": 25_000, "trial_days": 14,
        "limits": {"rpm": 300, "rph": 10_000, "rpd": 500_000, "tpm": 1_000_000, "tpd": 20_000_000,
                   "concurrency": 20, "monthly_token_quota": 200_000_000, "monthly_chat_messages": 20_000},
        "features": {"support": "priority", "analytics_retention_days": 90,
                     "byok": True, "priority_routing": True, "sla": None, "chat_enabled": True},
        "models": [],
    },
    {
        "slug": "team", "name": "Team", "sort_order": 40,
        "description": "Shared organization with higher throughput and seats.",
        "price_monthly_usd": 400.0, "price_yearly_usd": 4_000.0, "monthly_credits": 100_000, "trial_days": 14,
        "limits": {"rpm": 1_000, "rph": 40_000, "rpd": 2_000_000, "tpm": 5_000_000, "tpd": 100_000_000,
                   "concurrency": 50, "monthly_token_quota": 1_000_000_000, "monthly_chat_messages": 100_000},
        "features": {"support": "priority", "analytics_retention_days": 180,
                     "byok": True, "priority_routing": True, "sla": "99.5%", "seats": 10, "chat_enabled": True},
        "models": [],
    },
    {
        "slug": "enterprise", "name": "Enterprise", "sort_order": 50,
        "description": "Negotiated limits, dedicated support, and SLA. Uncapped by default.",
        "price_monthly_usd": 0.0, "price_yearly_usd": 0.0, "monthly_credits": 0, "trial_days": 0,
        "limits": {},  # unlimited — no ceilings seeded
        "features": {"support": "dedicated", "analytics_retention_days": 365,
                     "byok": True, "priority_routing": True, "sla": "99.9%", "seats": None,
                     "chat_enabled": True},
        "models": [],
    },
    {
        "slug": "custom", "name": "Custom", "sort_order": 60, "is_public": False,
        "description": "Bespoke plan configured per account by an administrator.",
        "price_monthly_usd": 0.0, "price_yearly_usd": 0.0, "monthly_credits": 0, "trial_days": 0,
        "limits": {},  # unlimited unless an admin adds explicit limits/overrides
        "features": {"support": "dedicated", "analytics_retention_days": 365,
                     "byok": True, "priority_routing": True, "sla": None, "chat_enabled": True},
        "models": [],
    },
]


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"


async def seed_models(session: AsyncSession) -> None:
    """Create any DEFAULT_MODELS whose public_id is not yet present and synchronize
    context_window / attributes for existing seeded models."""
    existing_models = {
        m.public_id: m for m in (await session.execute(select(Model))).scalars().all()
    }
    created = 0
    updated = 0
    for spec in DEFAULT_MODELS:
        pid = spec["public_id"]
        if pid in existing_models:
            model = existing_models[pid]
            if model.context_window != spec["context_window"]:
                model.context_window = spec["context_window"]
                updated += 1
            continue
        session.add(Model(enabled=True, supports_streaming=True, **spec))
        created += 1
    if created or updated:
        logger.info("seeded_models", extra={"created": created, "updated": updated})


async def seed_model_prices(session: AsyncSession) -> None:
    """Snapshot the current per-model price as the opening ModelPrice row so historical
    billing can always price against the rate in effect at request time (§53)."""
    count = (await session.execute(select(func.count()).select_from(ModelPrice))).scalar() or 0
    if count:
        return
    # Flush so any models added by seed_models() in this transaction are visible
    # (the session is configured autoflush=False).
    await session.flush()
    models = (await session.execute(select(Model))).scalars().all()
    for model in models:
        session.add(
            ModelPrice(
                model_public_id=model.public_id,
                input_price_per_1m=model.input_price_per_1m,
                output_price_per_1m=model.output_price_per_1m,
                effective_until=None,  # None = the currently-effective price
            )
        )
    logger.info("seeded_model_prices", extra={"count": len(models)})


async def seed_plans(session: AsyncSession) -> None:
    """Create the default subscription plans with their limits, features, and model access.
    Idempotent: only creates plans whose slug is not already present."""
    existing = set(
        (await session.execute(select(Plan.slug))).scalars().all()
    )
    created = 0
    for spec in DEFAULT_PLANS:
        if spec["slug"] in existing:
            continue
        plan = Plan(
            slug=spec["slug"],
            name=spec["name"],
            description=spec.get("description", ""),
            price_monthly_usd=spec.get("price_monthly_usd", 0.0),
            price_yearly_usd=spec.get("price_yearly_usd", 0.0),
            monthly_credits=spec.get("monthly_credits", 0),
            trial_days=spec.get("trial_days", 0),
            sort_order=spec.get("sort_order", 0),
            is_public=spec.get("is_public", True),
            active=True,
            archived=False,
        )
        session.add(plan)
        # A metric omitted from `limits` is left unlimited (no row).
        for metric, value in spec.get("limits", {}).items():
            if value is None:
                continue
            plan.limits.append(PlanLimit(metric=metric, value=value))
        # Feature values are wrapped as {"value": ...} to keep the JSON column an object.
        for key, value in spec.get("features", {}).items():
            plan.features.append(PlanFeature(key=key, value={"value": value}))
        for public_id in spec.get("models", []):
            plan.models.append(PlanModel(model_public_id=public_id))
        created += 1
    if created:
        logger.info("seeded_plans", extra={"count": created})


async def seed_provider(session: AsyncSession) -> None:
    """Create default ProviderConfig rows for providers missing from the table.
    Idempotent per provider name (openai keyed off env, notrack keyless)."""
    existing = set((await session.execute(select(ProviderConfig.name))).scalars().all())
    defaults = [
        {
            "name": "openai",
            "provider_type": settings.upstream_provider,
            "base_url": settings.upstream_base_url,
            "auth_mode": settings.upstream_auth_mode,
            "key_masked": _mask_key(settings.upstream_api_key),
            "timeout": settings.upstream_timeout,
            "max_retries": settings.upstream_max_retries,
        },
        {
            "name": "notrack",
            "provider_type": "notrack",
            "base_url": settings.notrack_base_url,
            "auth_mode": "none",
            "key_masked": "",
            "timeout": settings.upstream_timeout,
            "max_retries": settings.upstream_max_retries,
        },
    ]
    created = 0
    for spec in defaults:
        if spec["name"] in existing:
            continue
        session.add(ProviderConfig(last_status="unknown", **spec))
        created += 1
    if created:
        logger.info("seeded_provider", extra={"count": created})


async def seed_admin(session: AsyncSession) -> None:
    if not settings.admin_email or not settings.admin_password:
        return
    existing = await user_service.get_user_by_email(session, settings.admin_email)
    if existing is not None:
        return
    await user_service.create_user(
        session,
        email=settings.admin_email,
        password=settings.admin_password,
        name=settings.admin_name,
        role=UserRole.ADMIN,
        plan="enterprise",
        email_verified=True,
    )
    logger.info("seeded_admin", extra={"email": settings.admin_email})


async def ensure_super_admin(session: AsyncSession) -> None:
    """The platform owner is a ``super_admin`` (§2). If nobody holds that role yet,
    promote the configured admin account, else the earliest-created user. Idempotent."""
    existing = (
        await session.execute(
            select(func.count()).select_from(User).where(User.admin_role == AdminRole.SUPER_ADMIN)
        )
    ).scalar() or 0
    if existing:
        return
    owner: User | None = None
    if settings.admin_email:
        owner = await user_service.get_user_by_email(session, settings.admin_email)
    if owner is None:
        owner = (
            await session.execute(select(User).order_by(User.created_at).limit(1))
        ).scalars().first()
    if owner is None:
        return
    owner.admin_role = AdminRole.SUPER_ADMIN
    if owner.role != UserRole.ADMIN:
        owner.role = UserRole.ADMIN
    await session.flush()
    logger.info("promoted_super_admin", extra={"user_id": owner.id})


async def provision_accounts(session: AsyncSession) -> None:
    """Ensure every user has a personal organization + subscription (§4, §31) and that
    organization_id is stamped onto their existing projects/keys/usage. Idempotent and
    count-guarded inside the services, so it is safe to run on every startup."""
    await session.flush()  # make any just-seeded users visible (autoflush=False)
    provisioned = await organization_service.backfill_personal_orgs(session)
    await organization_service.backfill_org_ids(session)
    if provisioned:
        logger.info("provisioned_accounts", extra={"count": provisioned})


async def ensure_chat_model_defaults(session: AsyncSession) -> None:
    """Retrofit chat-product model flags onto pre-existing databases.

    The 0003 migration backfills ``public_chat``/``supports_vision`` as False, and
    ``seed_models`` only inserts MISSING models — so a database seeded before the chat
    product would have no public chat models at all. If none are public yet, apply the
    DEFAULT_MODELS flags (matched by public_id). Guarded on 'none public' so it runs once
    and never clobbers an admin's later allow-list decisions. Fresh DBs seed the flags
    directly (via ``seed_models``), so this no-ops there."""
    await session.flush()
    any_public = (
        await session.execute(select(func.count()).select_from(Model).where(Model.public_chat.is_(True)))
    ).scalar() or 0
    if any_public:
        return
    flags = {
        spec["public_id"]: (spec.get("public_chat", False), spec.get("supports_vision", False))
        for spec in DEFAULT_MODELS
    }
    changed = 0
    for model in (await session.execute(select(Model))).scalars().all():
        want_public, want_vision = flags.get(model.public_id, (False, False))
        if want_public and not model.public_chat:
            model.public_chat = True
            changed += 1
        if want_vision and not model.supports_vision:
            model.supports_vision = True
    if changed:
        await session.flush()
        logger.info("ensured_chat_model_defaults", extra={"count": changed})


async def ensure_chat_plan_defaults(session: AsyncSession) -> None:
    """Retrofit chat plan config onto pre-existing plans.

    ``seed_plans`` only creates MISSING plans, so already-seeded plans won't gain the
    ``chat_enabled`` feature or the ``monthly_chat_messages`` limit. Add only the rows that
    are MISSING (never overwrite an existing value). Idempotent per row. Queries the child
    rows directly to avoid async lazy-loading of relationships."""
    await session.flush()
    spec_by_slug = {spec["slug"]: spec for spec in DEFAULT_PLANS}
    added = 0
    for plan_id, slug in (await session.execute(select(Plan.id, Plan.slug))).all():
        spec = spec_by_slug.get(slug)
        if spec is None:
            continue
        features = spec.get("features", {})
        if "chat_enabled" in features:
            has_feature = (
                await session.execute(
                    select(func.count()).select_from(PlanFeature).where(
                        PlanFeature.plan_id == plan_id, PlanFeature.key == "chat_enabled"
                    )
                )
            ).scalar() or 0
            if not has_feature:
                session.add(
                    PlanFeature(plan_id=plan_id, key="chat_enabled",
                                value={"value": features["chat_enabled"]})
                )
                added += 1
        limits = spec.get("limits", {})
        if "monthly_chat_messages" in limits:
            has_limit = (
                await session.execute(
                    select(func.count()).select_from(PlanLimit).where(
                        PlanLimit.plan_id == plan_id, PlanLimit.metric == "monthly_chat_messages"
                    )
                )
            ).scalar() or 0
            if not has_limit:
                session.add(
                    PlanLimit(plan_id=plan_id, metric="monthly_chat_messages",
                              value=limits["monthly_chat_messages"])
                )
                added += 1
    if added:
        await session.flush()
        logger.info("ensured_chat_plan_defaults", extra={"count": added})


async def run_bootstrap(session: AsyncSession) -> None:
    await seed_models(session)
    await ensure_chat_model_defaults(session)
    await seed_model_prices(session)
    await seed_plans(session)
    await ensure_chat_plan_defaults(session)
    await seed_provider(session)
    await seed_admin(session)
    await ensure_super_admin(session)
    await provision_accounts(session)
    await session.commit()
