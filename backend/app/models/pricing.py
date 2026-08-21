"""Model price history (§53). Each row is a price *snapshot* effective over a time
window, so historical billing is always computed with the price that was in effect
then — never today's price. The current price for a model is the row with the latest
``effective_from`` and a null ``effective_until``."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.ids import new_id
from app.utils.time import utcnow


class ModelPrice(Base):
    __tablename__ = "model_prices"
    __table_args__ = (
        Index("ix_model_price_lookup", "model_public_id", "effective_from"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("price"))
    model_public_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)

    input_price_per_1m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    output_price_per_1m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # None = still in effect (the current price).
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
