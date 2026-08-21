"""Usage reads over the append-only ``usage_records`` table (the billing/analytics
source of truth). Usage rows are NEVER modified after the fact (§53); this module only
reads and aggregates them (writes go through :mod:`app.services.request_logger`).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageRecord


async def tokens_in_period(
    session: AsyncSession,
    *,
    organization_id: str | None = None,
    user_id: str | None = None,
    since: datetime,
    until: datetime | None = None,
    only_success: bool = True,
) -> int:
    """Total tokens billed in a window (used by the quota pre-flight gate). By default
    only successful requests count — failed/rate-limited rows must not consume quota."""
    stmt = select(func.coalesce(func.sum(UsageRecord.total_tokens), 0)).where(UsageRecord.ts >= since)
    if until is not None:
        stmt = stmt.where(UsageRecord.ts < until)
    if organization_id is not None:
        stmt = stmt.where(UsageRecord.organization_id == organization_id)
    if user_id is not None:
        stmt = stmt.where(UsageRecord.user_id == user_id)
    if only_success:
        stmt = stmt.where(UsageRecord.status == "success")
    return int((await session.execute(stmt)).scalar() or 0)


async def chat_messages_in_period(
    session: AsyncSession,
    *,
    api_key_id: str,
    since: datetime,
    until: datetime | None = None,
) -> int:
    """Count first-party chat turns billed in a window — one successful ``UsageRecord`` per
    turn on the caller's hidden chat system key. This is the append-only source of truth for
    the ``monthly_chat_messages`` plan quota (never a mutable counter). Only successful turns
    count; failed/rate-limited turns must not consume the quota."""
    stmt = (
        select(func.count())
        .select_from(UsageRecord)
        .where(
            UsageRecord.api_key_id == api_key_id,
            UsageRecord.ts >= since,
            UsageRecord.status == "success",
        )
    )
    if until is not None:
        stmt = stmt.where(UsageRecord.ts < until)
    return int((await session.execute(stmt)).scalar() or 0)


async def cost_in_period(
    session: AsyncSession,
    *,
    organization_id: str,
    since: datetime,
    until: datetime | None = None,
    only_success: bool = True,
) -> float:
    stmt = select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).where(
        UsageRecord.organization_id == organization_id, UsageRecord.ts >= since
    )
    if until is not None:
        stmt = stmt.where(UsageRecord.ts < until)
    if only_success:
        stmt = stmt.where(UsageRecord.status == "success")
    return float((await session.execute(stmt)).scalar() or 0.0)


async def usage_by_model(
    session: AsyncSession,
    *,
    organization_id: str,
    since: datetime,
    until: datetime,
    only_success: bool = True,
) -> list[dict]:
    """Per-model rollup for a window — the basis for invoice line items (§32). Only
    successful requests are billed by default."""
    stmt = (
        select(
            UsageRecord.model,
            func.count().label("requests"),
            func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
        )
        .where(
            UsageRecord.organization_id == organization_id,
            UsageRecord.ts >= since,
            UsageRecord.ts < until,
        )
        .group_by(UsageRecord.model)
        .order_by(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0).desc())
    )
    if only_success:
        stmt = stmt.where(UsageRecord.status == "success")
    rows = (await session.execute(stmt)).all()
    return [
        {
            "model": r[0] or "unknown",
            "requests": int(r[1] or 0),
            "prompt_tokens": int(r[2] or 0),
            "completion_tokens": int(r[3] or 0),
            "total_tokens": int(r[4] or 0),
            "cost_usd": round(float(r[5] or 0.0), 6),
        }
        for r in rows
    ]


async def summary(
    session: AsyncSession,
    *,
    organization_id: str | None = None,
    user_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """Aggregate totals (requests, tokens, cost, credits) for a scope/window."""
    stmt = select(
        func.count().label("requests"),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
        func.coalesce(func.sum(UsageRecord.credits_used), 0),
    )
    if organization_id is not None:
        stmt = stmt.where(UsageRecord.organization_id == organization_id)
    if user_id is not None:
        stmt = stmt.where(UsageRecord.user_id == user_id)
    if since is not None:
        stmt = stmt.where(UsageRecord.ts >= since)
    if until is not None:
        stmt = stmt.where(UsageRecord.ts < until)
    row = (await session.execute(stmt)).one()
    return {
        "requests": int(row[0] or 0),
        "total_tokens": int(row[1] or 0),
        "cost_usd": round(float(row[2] or 0.0), 6),
        "credits_used": int(row[3] or 0),
    }
