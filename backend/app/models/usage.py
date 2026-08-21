"""Usage records + pre-aggregated hourly rollups for fast analytics."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.ids import new_id
from app.utils.time import utcnow


class UsageRecord(Base):
    """One row per billable request (denormalized for aggregation)."""

    __tablename__ = "usage_records"
    __table_args__ = (
        Index("ix_usage_user_ts", "user_id", "ts"),
        Index("ix_usage_project_ts", "project_id", "ts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("use"))
    request_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Credits consumed by this request (0 when the org is not credit-gated).
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)

    # Price snapshot (USD per 1M tokens) used to compute cost_usd, so historical
    # billing never re-prices with today's rates (§53).
    input_price_snapshot: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    output_price_snapshot: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class UsageAggregate(Base):
    """Pre-aggregated rollup per (granularity, bucket, org, user, project, model) —
    powers dashboard charts cheaply. granularity ∈ hour|day|month."""

    __tablename__ = "usage_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "granularity", "bucket", "organization_id", "user_id", "project_id", "model",
            name="uq_usage_aggregate_bucket",
        ),
        Index("ix_usage_agg_bucket", "bucket"),
        Index("ix_usage_agg_gran_bucket", "granularity", "bucket"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("agg"))
    granularity: Mapped[str] = mapped_column(String(10), default="hour", nullable=False)
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # period-truncated
    organization_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    user_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    project_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_sum_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
