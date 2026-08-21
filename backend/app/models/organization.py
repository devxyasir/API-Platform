"""Organizations — the ownership entity for plans, subscriptions, credits, projects,
keys and usage. Every user gets an auto-created personal organization (OpenAI-style),
and organizations may also have multiple members."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import MemberStatus, OrgRole, OrgStatus
from app.utils.ids import new_id
from app.utils.time import utcnow


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)

    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default=OrgStatus.ACTIVE, nullable=False, index=True)

    # A personal org is auto-created for each user and cannot be deleted while the
    # user exists. Multi-member orgs are created explicitly.
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Cached mirror of the credit ledger (source of truth = credit_transactions).
    # Only CreditService mutates this, always alongside a ledger row.
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("mem"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), default=OrgRole.DEVELOPER, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=MemberStatus.ACTIVE, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()  # type: ignore  # noqa: F821
