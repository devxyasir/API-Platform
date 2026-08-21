"""User accounts (dashboard + API ownership)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.models.enums import AccountType, PlanSlug, UserRole, UserStatus
from app.utils.ids import new_id


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("usr"))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(20), default=UserRole.DEVELOPER, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(20), default=PlanSlug.FREE, nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), default=AccountType.FREE, nullable=False)

    # Platform-admin RBAC (§2). admin_role is None for non-admin users; admin_permissions
    # is an optional per-user override list layered on top of the role's default grants.
    admin_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    admin_permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Convenience pointer to the user's personal organization (see organizations).
    primary_org_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)

    # Monthly token quota (None = plan default). Enforced by the quota service.
    quota_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Legacy per-user credit mirror (deprecated — credit ledger is org-scoped now).
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Brute-force protection.
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore  # noqa: F821
    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")  # type: ignore  # noqa: F821

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.OWNER)

    @property
    def effective_quota(self) -> int | None:
        if self.quota_tokens is not None:
            return self.quota_tokens
        return None  # plan-derived quotas handled by the quota service
