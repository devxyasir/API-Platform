"""Credit ledger (§14). Append-only: the balance is the running sum of signed
amounts, and every mutation writes exactly one row carrying ``balance_after``.

``organizations.credit_balance`` is a cached mirror of the latest ``balance_after``
and is only ever updated by :mod:`app.services.credit_service` alongside a row here.
Credits, tokens, quota and money are SEPARATE concepts and never interchangeable (§58)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.ids import new_id
from app.utils.time import utcnow


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        Index("ix_credit_org_ts", "organization_id", "ts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ctx"))
    organization_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    type: Mapped[str] = mapped_column(String(20), nullable=False)  # CreditTxnType
    # Signed integer credits. Positive = added, negative = consumed/expired.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # Running balance immediately after applying this row.
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Free-form reference (request id, invoice id, admin action id, …).
    reference_id: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    # Grants may expire; expiration sweeps append a matching negative row.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)  # admin actor, if any
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
