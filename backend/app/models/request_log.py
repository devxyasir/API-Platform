"""Per-request logs (the observability backbone of the dashboard)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import RequestStatus, TokenCountSource
from app.utils.ids import request_id as gen_request_id
from app.utils.time import utcnow


class RequestLog(Base):
    __tablename__ = "requests"
    __table_args__ = (
        Index("ix_requests_user_started", "user_id", "started_at"),
        Index("ix_requests_project_started", "project_id", "started_at"),
        Index("ix_requests_status_started", "status", "started_at"),
        Index("ix_requests_model_started", "model", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=gen_request_id)

    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    model: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    upstream_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(80), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="POST", nullable=False)
    api_format: Mapped[str] = mapped_column(String(20), default="openai", nullable=False)  # openai|anthropic
    provider: Mapped[str] = mapped_column(String(60), default="openai", nullable=False)

    status: Mapped[str] = mapped_column(String(20), default=RequestStatus.SUCCESS, nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    stream: Mapped[bool] = mapped_column(default=False, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ttft_ms: Mapped[float | None] = mapped_column(Float, nullable=True)  # time to first token (streaming)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count_source: Mapped[str] = mapped_column(
        String(30), default=TokenCountSource.TOKENIZER_ESTIMATED, nullable=False
    )

    provider_request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)

    # Only populated when LOG_REQUEST_CONTENT is enabled (privacy).
    request_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
