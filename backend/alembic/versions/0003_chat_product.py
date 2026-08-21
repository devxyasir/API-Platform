"""chat product

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20 10:00:00.000000

Adds the first-party chat product's storage:
  * user_settings   — per-user chat preferences / custom instructions.
  * user_memories   — durable auto-extracted facts about the user.
  * embeddings      — semantic-recall index over message / summary snippets.
  * api_keys.is_system         — hidden per-user key backing the chat surface.
  * models.public_chat         — admin allow-list flag for public chat.
  * models.supports_vision     — whether image attachments are sent as vision parts.

New NOT NULL columns carry a ``server_default`` so existing rows backfill; the ORM
supplies the value for new rows. Fresh databases are created from metadata directly.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("custom_instructions_about", sa.Text(), nullable=False),
        sa.Column("custom_instructions_style", sa.Text(), nullable=False),
        sa.Column("preferred_model", sa.String(length=120), nullable=True),
        sa.Column("memory_enabled", sa.Boolean(), nullable=False),
        sa.Column("personalization_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_settings_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_settings_user_id"), ["user_id"], unique=True)

    op.create_table(
        "user_memories",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_conversation_id", sa.String(length=40), nullable=True),
        sa.Column("salience", sa.Float(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("user_memories", schema=None) as batch_op:
        batch_op.create_index("ix_user_memories_user_active", ["user_id", "active"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_memories_active"), ["active"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_memories_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_memories_source_conversation_id"), ["source_conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_memories_user_id"), ["user_id"], unique=False)

    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=40), nullable=False),
        sa.Column("owner_type", sa.String(length=30), nullable=False),
        sa.Column("owner_id", sa.String(length=40), nullable=False),
        sa.Column("conversation_id", sa.String(length=40), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("embeddings", schema=None) as batch_op:
        batch_op.create_index("ix_embeddings_user_owner", ["user_id", "owner_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_embeddings_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_embeddings_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_embeddings_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_embeddings_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f("ix_api_keys_is_system"), ["is_system"], unique=False)

    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_chat", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f("ix_models_public_chat"), ["public_chat"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_models_public_chat"))
        batch_op.drop_column("supports_vision")
        batch_op.drop_column("public_chat")

    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_keys_is_system"))
        batch_op.drop_column("is_system")

    with op.batch_alter_table("embeddings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_embeddings_user_id"))
        batch_op.drop_index(batch_op.f("ix_embeddings_owner_id"))
        batch_op.drop_index(batch_op.f("ix_embeddings_created_at"))
        batch_op.drop_index(batch_op.f("ix_embeddings_conversation_id"))
        batch_op.drop_index("ix_embeddings_user_owner")

    op.drop_table("embeddings")
    with op.batch_alter_table("user_memories", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_memories_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_memories_source_conversation_id"))
        batch_op.drop_index(batch_op.f("ix_user_memories_created_at"))
        batch_op.drop_index(batch_op.f("ix_user_memories_active"))
        batch_op.drop_index("ix_user_memories_user_active")

    op.drop_table("user_memories")
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_settings_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_settings_created_at"))

    op.drop_table("user_settings")
