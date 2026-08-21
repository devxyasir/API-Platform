"""Per-user chat preferences & personalization (§ chat product).

One row per user, created lazily on first access. Holds the "custom instructions"
that personalize every chat (in the ChatGPT sense) plus feature toggles. This is
distinct from account/billing state — it only shapes how the assistant responds.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id


class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("uset"))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    # "What should the assistant know about you?" / "How should it respond?" —
    # injected into the system context when personalization is enabled.
    custom_instructions_about: Mapped[str] = mapped_column(Text, default="", nullable=False)
    custom_instructions_style: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Default model for new conversations (public_id); None = server default.
    preferred_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Feature toggles the user controls for their own privacy/preference.
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
