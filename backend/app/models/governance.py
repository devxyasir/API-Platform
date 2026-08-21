"""Governance tables: temporary limit overrides (§24) and quota-reset events (§53).

A ``LimitOverride`` is a time-boxed override of a single metric at some scope,
resolved at the *highest* precedence by the limits resolver. ``QuotaResetEvent`` is
an append-only record of manual quota resets — usage rows are NEVER deleted (§53);
a reset just records the previous usage and starts a fresh counting anchor."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.ids import new_id
from app.utils.time import utcnow


class LimitOverride(Base):
    __tablename__ = "limit_overrides"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("lov"))
    # scope_type ∈ LIMIT_SCOPES; scope_id = entity id (or plan slug / "" for global).
    scope_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    scope_id: Mapped[str] = mapped_column(String(60), default="", index=True, nullable=False)

    metric: Mapped[str] = mapped_column(String(40), nullable=False)  # LIMIT_METRICS
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited

    # None = never expires; otherwise ignored once past.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class QuotaResetEvent(Base):
    __tablename__ = "quota_reset_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("qre"))
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    period: Mapped[str] = mapped_column(String(20), nullable=False)  # QuotaPeriod
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Counting anchor: usage before this instant is ignored for quota purposes.
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reset_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
