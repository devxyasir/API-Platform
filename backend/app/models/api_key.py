"""API keys. Raw keys are NEVER stored — only a salted hash + a display prefix."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.models.enums import DEFAULT_SCOPES, KeyStatus
from app.utils.ids import new_id


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("key"))
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Default key")

    # Only these are stored — the raw key is shown once at creation time.
    key_prefix: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )

    scopes: Mapped[list] = mapped_column(JSON, default=lambda: list(DEFAULT_SCOPES), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=KeyStatus.ACTIVE, nullable=False, index=True)

    # Hidden per-user key that backs the first-party chat product. It is provisioned
    # lazily, never displayed, and filtered out of every key-listing endpoint. It lets
    # the session-authed /account/chat surface reuse the exact /v1 enforcement pipeline
    # (rate limits, quotas, usage accounting) without a second, drift-prone code path.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Optional per-key overrides (None -> inherit from project/plan).
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")  # type: ignore  # noqa: F821
    project: Mapped["Project | None"] = relationship(back_populates="api_keys")  # type: ignore  # noqa: F821

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])
