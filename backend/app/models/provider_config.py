"""Provider configuration (upstream connection settings).

Secrets (API keys) are stored hashed/masked here for display; the *live* secret
used to call the upstream comes from environment configuration, never the DB
response. This table lets an admin see status and tweak non-secret settings.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id


class ProviderConfig(Base, TimestampMixin):
    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("prov"))
    name: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(60), default="openai", nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(20), default="bearer", nullable=False)
    # Masked hint of the configured key, e.g. "sk-...cD4f". NEVER the real secret.
    key_masked: Mapped[str] = mapped_column(String(60), default="", nullable=False)

    timeout: Mapped[float] = mapped_column(Float, default=120.0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    model_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Live health snapshot (updated by the health worker / circuit breaker).
    last_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    last_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
