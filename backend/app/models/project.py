"""Projects — a workspace grouping keys, usage and limits."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("proj"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)

    # Optional per-project overrides.
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    concurrency_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_token_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # List of model ids this project may use (empty -> all enabled models).
    allowed_models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    archived: Mapped[bool] = mapped_column(default=False, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="projects")  # type: ignore  # noqa: F821
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="project")  # type: ignore  # noqa: F821
