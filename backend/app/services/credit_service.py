"""Credit ledger (§14, §58, §59).

The ledger (``credit_transactions``) is append-only and the single source of truth.
Every mutation goes through :func:`_post`, which computes ``balance_after`` from the
organization's cached balance, writes exactly one row, and updates the cached mirror
``organizations.credit_balance`` in the same transaction. The mirror is therefore
never changed without a ledger entry (§59), and history is never edited — a correction
is a new ``ADJUSTMENT`` row, not a mutation of an old one.

Credits are a SEPARATE concept from tokens, quota, and money (§58): this module only
deals in signed integer credits.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.config import settings
from app.logging_config import get_logger
from app.models.credit import CreditTransaction
from app.models.enums import CreditTxnType
from app.models.organization import Organization

logger = get_logger("app.services.credit")


async def _load_org(session: AsyncSession, organization_id: str) -> Organization:
    # Row-lock the org on Postgres so concurrent posts serialize on balance; SQLite
    # has a single writer already and does not support SELECT ... FOR UPDATE.
    if settings.is_sqlite:
        org = await session.get(Organization, organization_id)
    else:
        org = await session.get(Organization, organization_id, with_for_update=True)
    if org is None:
        raise NotFoundError("Organization not found.", code="organization_not_found")
    return org


async def _post(
    session: AsyncSession,
    *,
    organization_id: str,
    amount: int,
    type: str,
    reason: str = "",
    user_id: str | None = None,
    reference_id: str | None = None,
    expires_at: datetime | None = None,
    created_by: str | None = None,
) -> CreditTransaction:
    """Append one ledger row and move the cached balance by ``amount`` (signed)."""
    org = await _load_org(session, organization_id)
    new_balance = int(org.credit_balance) + int(amount)
    txn = CreditTransaction(
        organization_id=organization_id,
        user_id=user_id,
        type=type,
        amount=int(amount),
        balance_after=new_balance,
        reason=reason,
        reference_id=reference_id,
        expires_at=expires_at,
        created_by=created_by,
    )
    session.add(txn)
    org.credit_balance = new_balance
    await session.flush()
    logger.info(
        "credit_txn",
        extra={"organization_id": organization_id, "type": type,
               "amount": amount, "balance_after": new_balance},
    )
    return txn


async def get_balance(session: AsyncSession, organization_id: str) -> int:
    org = await session.get(Organization, organization_id)
    return int(org.credit_balance) if org is not None else 0


async def has_credits(session: AsyncSession, organization_id: str, needed: int = 1) -> bool:
    return (await get_balance(session, organization_id)) >= needed


async def grant(
    session: AsyncSession,
    organization_id: str,
    amount: int,
    *,
    reason: str = "",
    type: str = CreditTxnType.GRANT,
    user_id: str | None = None,
    reference_id: str | None = None,
    expires_at: datetime | None = None,
    created_by: str | None = None,
) -> CreditTransaction:
    """Add credits (grant/bonus/purchase). ``amount`` must be positive."""
    if amount <= 0:
        raise ValueError("grant amount must be positive")
    return await _post(
        session, organization_id=organization_id, amount=amount, type=type,
        reason=reason, user_id=user_id, reference_id=reference_id,
        expires_at=expires_at, created_by=created_by,
    )


async def consume(
    session: AsyncSession,
    organization_id: str,
    amount: int,
    *,
    reason: str = "",
    user_id: str | None = None,
    reference_id: str | None = None,
) -> CreditTransaction:
    """Deduct credits for usage. ``amount`` is the (positive) number to consume; the
    ledger row is stored with a negative amount."""
    if amount <= 0:
        raise ValueError("consume amount must be positive")
    return await _post(
        session, organization_id=organization_id, amount=-amount, type=CreditTxnType.USAGE,
        reason=reason, user_id=user_id, reference_id=reference_id,
    )


async def refund(
    session: AsyncSession,
    organization_id: str,
    amount: int,
    *,
    reason: str = "",
    user_id: str | None = None,
    reference_id: str | None = None,
    created_by: str | None = None,
) -> CreditTransaction:
    if amount <= 0:
        raise ValueError("refund amount must be positive")
    return await _post(
        session, organization_id=organization_id, amount=amount, type=CreditTxnType.REFUND,
        reason=reason, user_id=user_id, reference_id=reference_id, created_by=created_by,
    )


async def adjust(
    session: AsyncSession,
    organization_id: str,
    delta: int,
    *,
    reason: str,
    user_id: str | None = None,
    created_by: str | None = None,
) -> CreditTransaction:
    """Manual signed correction by an admin (§59: correction = new row, not an edit)."""
    if delta == 0:
        raise ValueError("adjustment delta must be non-zero")
    return await _post(
        session, organization_id=organization_id, amount=delta, type=CreditTxnType.ADJUSTMENT,
        reason=reason, user_id=user_id, created_by=created_by,
    )


async def expire(
    session: AsyncSession,
    organization_id: str,
    amount: int,
    *,
    reason: str = "credit expiration",
    reference_id: str | None = None,
) -> CreditTransaction:
    """Expire ``amount`` credits (stored negative), e.g. when a grant passes expires_at."""
    if amount <= 0:
        raise ValueError("expire amount must be positive")
    return await _post(
        session, organization_id=organization_id, amount=-amount, type=CreditTxnType.EXPIRATION,
        reason=reason, reference_id=reference_id,
    )


async def ledger(
    session: AsyncSession, organization_id: str, *, limit: int = 50, offset: int = 0
) -> tuple[list[CreditTransaction], int]:
    total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.organization_id == organization_id)
            )
        ).scalar()
        or 0
    )
    rows = (
        await session.execute(
            select(CreditTransaction)
            .where(CreditTransaction.organization_id == organization_id)
            .order_by(CreditTransaction.ts.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def recompute_balance(session: AsyncSession, organization_id: str) -> int:
    """Sum the ledger from scratch (integrity check / repair). Not used on the hot path."""
    total = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0))
                .where(CreditTransaction.organization_id == organization_id)
            )
        ).scalar()
        or 0
    )
    return total
