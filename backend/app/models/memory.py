"""Long-term memory & semantic-recall storage (§ chat product).

Two tables, both user-scoped:

* ``UserMemory`` — durable facts about the user, auto-extracted from conversations
  (or added manually) and shown on the Memories page for review/edit/delete. These
  are injected as a "what I know about you" block, ranked by embedding similarity to
  the current turn so even low-context models get only the most relevant few.
* ``Embedding`` — a generic recall index over message / conversation-summary snippets.
  Vectors live as JSON ``list[float]`` (consistent with the app's other JSON columns
  and avoiding a native vector-extension dependency); at personal scale an O(N) cosine
  over one user's rows is sub-millisecond.

All recall is best-effort: if embeddings are disabled or the upstream is unavailable,
these tables are simply skipped and chat still works.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin
from app.utils.ids import new_id


class UserMemory(Base, TimestampMixin):
    __tablename__ = "user_memories"
    __table_args__ = (Index("ix_user_memories_user_active", "user_id", "active"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("mem"))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Conversation this fact was learned from (kept for provenance; nulled if it's deleted).
    source_conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True
    )

    salience: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list[float]
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class Embedding(Base, TimestampMixin):
    __tablename__ = "embeddings"
    __table_args__ = (
        Index("ix_embeddings_user_owner", "user_id", "owner_type"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("emb"))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Polymorphic owner (no FK — owner_id is a message id or conversation id).
    owner_type: Mapped[str] = mapped_column(String(30), nullable=False)  # message|conversation_summary
    owner_id: Mapped[str] = mapped_column(String(40), index=True, nullable=False)

    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)  # the snippet that was embedded
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)  # list[float]
    model: Mapped[str] = mapped_column(String(120), nullable=False)  # embedding model id
