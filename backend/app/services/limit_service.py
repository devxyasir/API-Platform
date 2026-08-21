"""Effective-limit resolution across plan limits and time-boxed overrides (§24).

Precedence (lowest → highest): plan limits → limit overrides applied in scope order
(global → plan → organization → user → project → api_key → model). A ``LimitOverride``
with a value of ``None`` means *unlimited* for that metric; an expired override is
ignored. This module is the single reader of ``plan_limits`` + ``limit_overrides`` and
is used by both the rate-limit resolver (LimitSet fields) and the quota service
(monthly/daily token quotas)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.enums import LIMIT_METRICS
from app.models.governance import LimitOverride
from app.services import plan_service
from app.utils.time import utcnow


async def plan_metric_map(session: AsyncSession, plan_slug: str) -> dict[str, int | None]:
    plan = await plan_service.get_plan_by_slug(session, plan_slug)
    if plan is None:
        return {}
    return await plan_service.limit_map(session, plan.id)


async def override_map(
    session: AsyncSession, scope_pairs: list[tuple[str, str]], *, now: datetime | None = None
) -> dict[str, int | None]:
    """{metric: value} from non-expired overrides matching the scope pairs, with later
    pairs winning. ``value`` may be None (explicitly unlimited)."""
    if not scope_pairs:
        return {}
    now = now or utcnow()
    rows = (
        await session.execute(
            select(LimitOverride).where(
                or_(
                    *[
                        and_(LimitOverride.scope_type == st, LimitOverride.scope_id == sid)
                        for st, sid in scope_pairs
                    ]
                ),
                or_(LimitOverride.expires_at.is_(None), LimitOverride.expires_at > now),
            )
        )
    ).scalars().all()
    # Rank each row by its scope position so higher-precedence scopes win.
    rank = {pair: i for i, pair in enumerate(scope_pairs)}
    best: dict[str, tuple[int, int | None]] = {}
    for r in rows:
        pos = rank.get((r.scope_type, r.scope_id))
        if pos is None:
            continue
        if r.metric not in best or pos >= best[r.metric][0]:
            best[r.metric] = (pos, r.value)
    return {metric: value for metric, (_, value) in best.items()}


async def effective_limits(
    session: AsyncSession,
    *,
    plan_slug: str,
    scope_pairs: list[tuple[str, str]],
    now: datetime | None = None,
) -> dict[str, int | None]:
    """Merge plan limits with overrides. Only metrics that are actually configured
    (by the plan or an override) appear; an absent metric means unlimited."""
    merged: dict[str, int | None] = dict(await plan_metric_map(session, plan_slug))
    for metric, value in (await override_map(session, scope_pairs, now=now)).items():
        merged[metric] = value
    return merged


async def effective_metric(
    session: AsyncSession,
    metric: str,
    *,
    plan_slug: str,
    scope_pairs: list[tuple[str, str]],
    now: datetime | None = None,
) -> int | None:
    """Effective value of a single metric, or None if unlimited/unconfigured."""
    over = await override_map(session, scope_pairs, now=now)
    if metric in over:
        return over[metric]
    plan = await plan_metric_map(session, plan_slug)
    return plan.get(metric)


# --- admin CRUD for overrides ------------------------------------------------
async def create_override(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: str,
    metric: str,
    value: int | None,
    expires_at: datetime | None = None,
    reason: str = "",
    created_by: str | None = None,
) -> LimitOverride:
    override = LimitOverride(
        scope_type=scope_type, scope_id=scope_id or "", metric=metric, value=value,
        expires_at=expires_at, reason=reason, created_by=created_by,
    )
    session.add(override)
    await session.flush()
    return override


async def list_overrides(
    session: AsyncSession,
    *,
    scope_type: str | None = None,
    scope_id: str | None = None,
    include_expired: bool = True,
    now: datetime | None = None,
) -> list[LimitOverride]:
    stmt = select(LimitOverride)
    if scope_type is not None:
        stmt = stmt.where(LimitOverride.scope_type == scope_type)
    if scope_id is not None:
        stmt = stmt.where(LimitOverride.scope_id == scope_id)
    if not include_expired:
        now = now or utcnow()
        stmt = stmt.where(
            or_(LimitOverride.expires_at.is_(None), LimitOverride.expires_at > now)
        )
    stmt = stmt.order_by(LimitOverride.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def delete_override(session: AsyncSession, override_id: str) -> None:
    override = await session.get(LimitOverride, override_id)
    if override is None:
        raise NotFoundError("Limit override not found.", code="override_not_found")
    await session.delete(override)
    await session.flush()


def is_known_metric(metric: str) -> bool:
    return metric in LIMIT_METRICS
