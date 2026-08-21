"""Model registry — maps public model ids/aliases to an upstream provider model."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id


class Model(Base, TimestampMixin):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("public_id", name="uq_models_public_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("mdl"))

    # The id customers pass in `model` field, e.g. "gpt-4o" or an alias "fast".
    public_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    provider: Mapped[str] = mapped_column(String(60), default="openai", nullable=False)
    # The model id actually sent to the upstream provider.
    upstream_model: Mapped[str] = mapped_column(String(120), nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Governance for the first-party chat product. ``public_chat`` is the admin-controlled
    # allow-list flag deciding whether a model may be offered in the public chat UI (a model
    # can be enabled for /v1 API use yet withheld from public chat). ``supports_vision`` gates
    # whether image attachments are sent as vision parts; when false, the chat surface refuses
    # image uploads for this model (documents still work via the markitdown text path).
    public_chat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Aliases pointing to this model, e.g. ["default", "fast"].
    aliases: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Optional pricing metadata (USD per 1M tokens) for cost estimates.
    input_price_per_1m: Mapped[float] = mapped_column(default=0.0, nullable=False)
    output_price_per_1m: Mapped[float] = mapped_column(default=0.0, nullable=False)
