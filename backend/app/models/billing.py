"""Invoices for the billing simulation (§32-33). Generated per billing period from
usage price snapshots + the plan fee. No real payment provider — a ``BillingProvider``
abstraction (see :mod:`app.services.billing_service`) lets a real one plug in later."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.models.enums import InvoiceStatus
from app.utils.ids import new_id


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoice_org_period", "organization_id", "period_start"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("inv"))
    organization_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=InvoiceStatus.DRAFT, nullable=False, index=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    plan_fee_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    usage_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    credits_applied_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Snapshot line items: [{description, quantity, unit, amount_usd}, …].
    line_items: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
