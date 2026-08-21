"""Model price snapshots (§53).

Historical billing must always price against the rate that was in effect at request
time, never today's price. Each :class:`ModelPrice` row is a price effective over a
half-open window ``[effective_from, effective_until)``; the current price is the row
with ``effective_until IS NULL``. Changing a price closes the current row and opens a
new one — rows are never edited in place.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model
from app.models.pricing import ModelPrice
from app.utils.time import utcnow


def compute_cost(input_price_per_1m: float, output_price_per_1m: float,
                 prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost for a request given a price snapshot (per 1M tokens)."""
    return round(
        prompt_tokens / 1_000_000 * input_price_per_1m
        + completion_tokens / 1_000_000 * output_price_per_1m,
        6,
    )


async def effective_price_row(
    session: AsyncSession, model_public_id: str, at: datetime | None = None
) -> ModelPrice | None:
    """The price row in effect for a model at instant ``at`` (default: now)."""
    at = at or utcnow()
    result = await session.execute(
        select(ModelPrice)
        .where(
            ModelPrice.model_public_id == model_public_id,
            ModelPrice.effective_from <= at,
        )
        .order_by(ModelPrice.effective_from.desc())
    )
    for row in result.scalars():
        # First (most recent effective_from) whose window still contains `at`.
        if row.effective_until is None or row.effective_until > at:
            return row
    return None


async def snapshot_for(
    session: AsyncSession, model: Model, at: datetime | None = None
) -> tuple[float, float]:
    """(input_per_1m, output_per_1m) to bill a request with, falling back to the
    model's own current price columns when no snapshot row exists yet."""
    row = await effective_price_row(session, model.public_id, at)
    if row is not None:
        return row.input_price_per_1m, row.output_price_per_1m
    return model.input_price_per_1m, model.output_price_per_1m


async def current_prices(session: AsyncSession) -> list[ModelPrice]:
    """The currently-effective price row for every model that has one."""
    result = await session.execute(
        select(ModelPrice)
        .where(ModelPrice.effective_until.is_(None))
        .order_by(ModelPrice.model_public_id)
    )
    return list(result.scalars().all())


async def price_history(session: AsyncSession, model_public_id: str) -> list[ModelPrice]:
    result = await session.execute(
        select(ModelPrice)
        .where(ModelPrice.model_public_id == model_public_id)
        .order_by(ModelPrice.effective_from.desc())
    )
    return list(result.scalars().all())


async def set_price(
    session: AsyncSession,
    *,
    model_public_id: str,
    input_price_per_1m: float,
    output_price_per_1m: float,
    created_by: str | None = None,
    at: datetime | None = None,
) -> ModelPrice:
    """Open a new current price, closing the previous one at the same instant so the
    timeline stays contiguous. Also mirrors onto the Model row (its cached price)."""
    now = at or utcnow()
    current = await effective_price_row(session, model_public_id, now)
    if current is not None and current.effective_until is None:
        current.effective_until = now
    row = ModelPrice(
        model_public_id=model_public_id,
        input_price_per_1m=input_price_per_1m,
        output_price_per_1m=output_price_per_1m,
        effective_from=now,
        effective_until=None,
        created_by=created_by,
    )
    session.add(row)
    # Keep the Model's convenience columns in step with the current snapshot.
    model = (
        await session.execute(select(Model).where(Model.public_id == model_public_id))
    ).scalar_one_or_none()
    if model is not None:
        model.input_price_per_1m = input_price_per_1m
        model.output_price_per_1m = output_price_per_1m
    await session.flush()
    return row
