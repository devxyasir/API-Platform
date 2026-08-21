"""Subscriptions bind an organization to a plan over billing periods (§31), plus an
append-only plan-change history (§12)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import SubscriptionStatus, TrialStatus
from app.utils.ids import new_id
from app.utils.time import utcnow


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("sub"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=SubscriptionStatus.ACTIVE, nullable=False, index=True
    )

    # Billing provider abstraction — "manual" for the local billing simulation.
    provider: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    external_subscription_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    trial_status: Mapped[str] = mapped_column(String(20), default=TrialStatus.NONE, nullable=False)
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["Plan"] = relationship()  # type: ignore  # noqa: F821


class PlanHistory(Base):
    """Append-only record of every plan change for an organization (§12)."""

    __tablename__ = "plan_history"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("phist"))
    organization_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    old_plan: Mapped[str | None] = mapped_column(String(60), nullable=True)
    new_plan: Mapped[str] = mapped_column(String(60), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
