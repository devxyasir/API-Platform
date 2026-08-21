"""Security & risk events (§38, §41). Both append-only audit-style tables.

``SecurityEvent`` records authentication / access-control events. ``RiskEvent``
records abuse-detection findings from the risk_service sweeps."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base
from app.models.enums import RiskStatus, SecurityEventStatus, Severity
from app.utils.ids import new_id
from app.utils.time import utcnow


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_event_ts", "ts"),
        Index("ix_security_event_user_ts", "user_id", "ts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("sec"))
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # SecurityEventType
    status: Mapped[str] = mapped_column(String(20), default=SecurityEventStatus.OPEN, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default=Severity.INFO, nullable=False)

    ip_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class RiskEvent(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        Index("ix_risk_event_ts", "ts"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("risk"))
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    organization_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # RiskEventType
    severity: Mapped[str] = mapped_column(String(20), default=Severity.LOW, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=RiskStatus.OPEN, nullable=False, index=True)

    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
