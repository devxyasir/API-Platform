"""Rate-limit configuration overrides and violation events."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id
from app.utils.time import utcnow


class RateLimitConfig(Base, TimestampMixin):
    """A configurable limit set at a given scope level.

    scope_type: global | plan | user | project | api_key | model
    scope_id:   "" for global, the plan name, or the entity id.
    """

    __tablename__ = "rate_limit_configs"
    __table_args__ = (UniqueConstraint("scope_type", "scope_id", name="uq_rate_limit_scope"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rl"))
    scope_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    scope_id: Mapped[str] = mapped_column(String(60), default="", nullable=False, index=True)

    rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rph: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RateLimitEvent(Base):
    """Recorded whenever a request is throttled (for analytics)."""

    __tablename__ = "rate_limit_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rle"))
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    limit_type: Mapped[str] = mapped_column(String(30), nullable=False)  # rpm|tpm|concurrency|...
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    limit_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
