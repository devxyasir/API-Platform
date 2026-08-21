"""Token-quota enforcement (§54).

Longer-window token quotas (``monthly_token_quota`` / ``daily_token_quota``) are
enforced as a REAL pre-flight gate here, computed from append-only usage — NOT via the
rate-limiter's ``tpm``/``tpd`` (which are soft/peek-only, so a single over-budget
request still runs once). Exceeding a quota raises a 429 ``token_quota_exceeded``.

The window start is the current billing period (subscription) for monthly quota and
UTC midnight for daily quota, each moved forward to the latest manual quota-reset
anchor (§53) so a reset takes effect without ever deleting usage rows.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import ChatQuotaExceededError, TokenQuotaExceededError
from app.models.governance import QuotaResetEvent
from app.models.subscription import Subscription
from app.services import limit_service, usage_service
from app.utils.time import day_start, ensure_aware, month_start, utcnow

# (metric, period-kind) pairs enforced on every request.
_QUOTA_METRICS = (("monthly_token_quota", "month"), ("daily_token_quota", "day"))


def _scope_pairs(plan_slug: str, organization_id: str, user_id: str | None) -> list[tuple[str, str]]:
    pairs = [("global", ""), ("plan", plan_slug), ("organization", organization_id)]
    if user_id:
        pairs.append(("user", user_id))
    return pairs


async def _reset_anchor(
    session: AsyncSession, organization_id: str, metric: str
) -> datetime | None:
    val = (
        await session.execute(
            select(func.max(QuotaResetEvent.reset_at)).where(
                QuotaResetEvent.organization_id == organization_id,
                QuotaResetEvent.metric == metric,
            )
        )
    ).scalar()
    return ensure_aware(val)


async def _subscription_period_start(session: AsyncSession, organization_id: str) -> datetime:
    sub = (
        await session.execute(
            select(Subscription)
            .where(Subscription.organization_id == organization_id)
            .order_by(Subscription.created_at.desc())
        )
    ).scalars().first()
    if sub is not None and sub.current_period_start is not None:
        return ensure_aware(sub.current_period_start)
    return month_start()


async def period_start(
    session: AsyncSession, organization_id: str, kind: str, metric: str
) -> datetime:
    if kind == "month":
        start = await _subscription_period_start(session, organization_id)
    else:
        start = day_start()
    anchor = await _reset_anchor(session, organization_id, metric)
    if anchor is not None and anchor > start:
        start = anchor
    return start


async def _metric_limit(
    session: AsyncSession, metric: str, *, plan_slug: str, organization_id: str, user_id: str | None
) -> int | None:
    return await limit_service.effective_metric(
        session, metric, plan_slug=plan_slug,
        scope_pairs=_scope_pairs(plan_slug, organization_id, user_id),
    )


async def check_tokens(
    session: AsyncSession,
    *,
    organization_id: str,
    plan_slug: str,
    user_id: str | None = None,
    incoming_tokens: int = 0,
) -> None:
    """Raise :class:`TokenQuotaExceededError` if this request would exceed a token
    quota. No-op when quota enforcement is disabled or the quota is unlimited."""
    if not settings.token_quota_enforced:
        return
    for metric, kind in _QUOTA_METRICS:
        limit = await _metric_limit(
            session, metric, plan_slug=plan_slug, organization_id=organization_id, user_id=user_id
        )
        if limit is None:
            continue  # unlimited / unconfigured
        since = await period_start(session, organization_id, kind, metric)
        used = await usage_service.tokens_in_period(
            session, organization_id=organization_id, since=since
        )
        if used + incoming_tokens > limit:
            raise TokenQuotaExceededError(
                f"Token quota exceeded ({metric}). Used {used} of {limit} for the current "
                f"{kind}.",
                extra={"metric": metric, "limit": limit, "used": used, "period": kind},
            )


async def check_chat_messages(
    session: AsyncSession,
    *,
    organization_id: str,
    plan_slug: str,
    api_key_id: str,
    user_id: str | None = None,
    incoming: int = 1,
) -> None:
    """Raise :class:`ChatQuotaExceededError` if this chat turn would exceed the plan's
    ``monthly_chat_messages`` allowance. No-op when the plan leaves the metric unlimited.

    This is a first-party chat-product gate that lives ABOVE ``chat_service.prepare`` — it is
    never applied to ``/v1``. The count is derived from append-only usage on the caller's
    hidden chat system key (one successful turn = one message), so it can't drift from a
    counter and it honours the same manual-reset anchor as the token quota."""
    limit = await _metric_limit(
        session, "monthly_chat_messages", plan_slug=plan_slug,
        organization_id=organization_id, user_id=user_id,
    )
    if limit is None:
        return  # unlimited / unconfigured
    since = await period_start(session, organization_id, "month", "monthly_chat_messages")
    used = await usage_service.chat_messages_in_period(session, api_key_id=api_key_id, since=since)
    if used + incoming > limit:
        raise ChatQuotaExceededError(
            f"You've reached your plan's monthly chat message limit ({used} of {limit}). "
            f"Upgrade your plan or wait for the next billing period.",
            extra={"metric": "monthly_chat_messages", "limit": limit, "used": used},
        )


async def chat_message_status(
    session: AsyncSession,
    *,
    organization_id: str,
    plan_slug: str,
    api_key_id: str,
    user_id: str | None = None,
) -> dict:
    """Dashboard/chat-UI view of the monthly chat-message allowance for an organization."""
    limit = await _metric_limit(
        session, "monthly_chat_messages", plan_slug=plan_slug,
        organization_id=organization_id, user_id=user_id,
    )
    since = await period_start(session, organization_id, "month", "monthly_chat_messages")
    used = await usage_service.chat_messages_in_period(session, api_key_id=api_key_id, since=since)
    return {
        "metric": "monthly_chat_messages",
        "limit": limit,
        "used": used,
        "remaining": None if limit is None else max(0, limit - used),
        "unlimited": limit is None,
        "period_start": since,
    }


async def quota_status(
    session: AsyncSession,
    *,
    organization_id: str,
    plan_slug: str,
    user_id: str | None = None,
) -> dict:
    """Dashboard view of the monthly token quota for an organization."""
    limit = await _metric_limit(
        session, "monthly_token_quota", plan_slug=plan_slug,
        organization_id=organization_id, user_id=user_id,
    )
    since = await period_start(session, organization_id, "month", "monthly_token_quota")
    used = await usage_service.tokens_in_period(
        session, organization_id=organization_id, since=since
    )
    return {
        "metric": "monthly_token_quota",
        "limit": limit,
        "used": used,
        "remaining": None if limit is None else max(0, limit - used),
        "unlimited": limit is None,
        "period_start": since,
    }


async def reset_quota(
    session: AsyncSession,
    *,
    organization_id: str,
    user_id: str | None = None,
    metric: str = "monthly_token_quota",
    period: str = "month",
    reason: str = "",
    reset_by: str | None = None,
) -> QuotaResetEvent:
    """Record a manual quota reset (§53). Usage rows are NOT deleted — the reset just
    stores the previous usage and starts a fresh counting anchor at ``now``."""
    now = utcnow()
    kind = "day" if period == "day" else "month"
    since = await period_start(session, organization_id, kind, metric)
    previous = await usage_service.tokens_in_period(
        session, organization_id=organization_id, since=since
    )
    event = QuotaResetEvent(
        user_id=user_id,
        organization_id=organization_id,
        period=period,
        metric=metric,
        previous_usage=previous,
        reset_at=now,
        reset_by=reset_by,
        reason=reason,
    )
    session.add(event)
    await session.flush()
    return event
