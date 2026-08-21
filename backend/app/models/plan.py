"""Subscription plans stored in the database (§8-12).

A ``Plan`` is a named tier (Free/Pro/Team/…) with:
- structured limits (:class:`PlanLimit`, one row per metric),
- feature flags/values (:class:`PlanFeature`),
- an allow-list of models (:class:`PlanModel`; empty = all enabled models).

Plans are versioned by soft-archive — a plan with subscription/billing history is
never hard-deleted (§53)."""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("plan"))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    price_monthly_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_yearly_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Credits granted on each billing period (0 = none).
    monthly_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Trial length in days for new subscriptions (0 = no trial).
    trial_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    limits: Mapped[list["PlanLimit"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    features: Mapped[list["PlanFeature"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    models: Mapped[list["PlanModel"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class PlanLimit(Base):
    """One limit metric for a plan (metric ∈ LIMIT_METRICS). value None = unlimited."""

    __tablename__ = "plan_limits"
    __table_args__ = (UniqueConstraint("plan_id", "metric", name="uq_plan_limit"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("plim"))
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)

    plan: Mapped["Plan"] = relationship(back_populates="limits")


class PlanFeature(Base):
    """A feature flag/value for a plan (value is arbitrary JSON)."""

    __tablename__ = "plan_features"
    __table_args__ = (UniqueConstraint("plan_id", "key", name="uq_plan_feature"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("pfeat"))
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    plan: Mapped["Plan"] = relationship(back_populates="features")


class PlanModel(Base):
    """A model this plan may access (references Model.public_id). No rows = all
    enabled models allowed."""

    __tablename__ = "plan_models"
    __table_args__ = (UniqueConstraint("plan_id", "model_public_id", name="uq_plan_model"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("pmod"))
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_public_id: Mapped[str] = mapped_column(String(120), nullable=False)

    plan: Mapped["Plan"] = relationship(back_populates="models")
