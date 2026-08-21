"""Resolve the effective rate-limit set for an authenticated caller.

Precedence (later overrides earlier, per-field): hard-coded plan defaults →
DB plan limits → global config → plan config → user config → project config →
per-project columns → API-key config → per-key columns → time-boxed limit overrides.
"""
from __future__ import annotations

from dataclasses import replace

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.api_key import ApiKey
from app.models.project import Project
from app.models.rate_limit import RateLimitConfig
from app.models.user import User
from app.rate_limit.limiter import LimitSet
from app.services import limit_service

# Sensible per-plan defaults (see spec §10) used only as a fallback when a plan has no
# DB limit rows. Enterprise is effectively unlimited.
PLAN_LIMITS: dict[str, LimitSet] = {
    "free": LimitSet(rpm=20, rpd=10_000, tpd=100_000, concurrency=3),
    "starter": LimitSet(rpm=60, rpd=50_000, tpd=500_000, concurrency=5),
    "pro": LimitSet(rpm=300, rpd=500_000, tpd=1_000_000, concurrency=20),
    "enterprise": LimitSet(concurrency=settings.global_concurrency),
}

# LimitSet fields that map 1:1 to limit metrics.
_LIMITSET_METRICS = ("rpm", "rph", "rpd", "tpm", "tpd", "concurrency")


def _merge(base: LimitSet, override: LimitSet | RateLimitConfig | ApiKey | Project) -> LimitSet:
    fields = {}
    for f in _LIMITSET_METRICS:
        val = getattr(override, f, None)
        if val is not None:
            fields[f] = val
    return replace(base, **fields)


def _apply_map(base: LimitSet, metric_map: dict[str, int | None]) -> LimitSet:
    """Apply a {metric: value} map to the LimitSet fields. Unlike :func:`_merge`, a
    value of ``None`` is applied verbatim (meaning *unlimited* for that field), because
    plan limits and overrides use None to mean unlimited rather than "inherit"."""
    fields = {f: metric_map[f] for f in _LIMITSET_METRICS if f in metric_map}
    return replace(base, **fields)


def _default_plan_limits(plan: str) -> LimitSet:
    return replace(PLAN_LIMITS.get(plan, PLAN_LIMITS["free"]))


async def resolve_limits(session: AsyncSession, *, user: User, api_key: ApiKey,
                         project: Project | None) -> LimitSet:
    # Base: hard-coded plan defaults, then DB plan limits layered on top.
    limits = _default_plan_limits(user.plan)
    limits = _apply_map(limits, await limit_service.plan_metric_map(session, user.plan))

    scope_pairs = [
        ("global", ""),
        ("plan", user.plan),
        ("user", user.id),
    ]
    if project is not None:
        scope_pairs.append(("project", project.id))
    scope_pairs.append(("api_key", api_key.id))

    result = await session.execute(
        select(RateLimitConfig).where(
            or_(
                *[
                    and_(RateLimitConfig.scope_type == st, RateLimitConfig.scope_id == sid)
                    for st, sid in scope_pairs
                ]
            )
        )
    )
    configs = {(c.scope_type, c.scope_id): c for c in result.scalars().all()}

    # Apply configs in precedence order.
    for st, sid in scope_pairs:
        cfg = configs.get((st, sid))
        if cfg is not None:
            limits = _merge(limits, cfg)

    # Per-project and per-key column overrides.
    if project is not None:
        limits = _merge(
            limits,
            LimitSet(rpm=project.rpm_limit, tpm=project.tpm_limit, concurrency=project.concurrency_limit),
        )
    limits = _merge(limits, LimitSet(rpm=api_key.rpm_limit, tpm=api_key.tpm_limit))

    # Highest precedence: time-boxed limit overrides (§24).
    org_id = getattr(api_key, "organization_id", None) or getattr(user, "primary_org_id", None)
    override_pairs: list[tuple[str, str]] = [("global", ""), ("plan", user.plan)]
    if org_id:
        override_pairs.append(("organization", org_id))
    override_pairs.append(("user", user.id))
    if project is not None:
        override_pairs.append(("project", project.id))
    override_pairs.append(("api_key", api_key.id))
    limits = _apply_map(limits, await limit_service.override_map(session, override_pairs))

    return limits

