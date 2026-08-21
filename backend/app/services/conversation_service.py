"""Conversation persistence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import NotFoundError
from app.models.conversation import Conversation, Message
from app.utils.time import utcnow


async def create_conversation(session: AsyncSession, *, user_id: str, title: str = "New conversation",
                              project_id: str | None = None, model: str | None = None) -> Conversation:
    conv = Conversation(user_id=user_id, title=title, project_id=project_id, model=model)
    session.add(conv)
    await session.flush()
    return conv


async def get_conversation(session: AsyncSession, conv_id: str, *, user_id: str,
                           with_messages: bool = False) -> Conversation:
    stmt = select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user_id)
    if with_messages:
        stmt = stmt.options(selectinload(Conversation.messages))
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if conv is None:
        raise NotFoundError("Conversation not found.")
    return conv


async def list_conversations(session: AsyncSession, *, user_id: str) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def add_message(session: AsyncSession, *, conversation_id: str, role: str, content: str,
                      tokens: int = 0) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content, tokens=tokens)
    session.add(msg)
    await session.flush()
    return msg


async def delete_conversation(session: AsyncSession, conv: Conversation) -> None:
    await session.delete(conv)
    await session.flush()


async def rename_conversation(session: AsyncSession, conv: Conversation, title: str) -> Conversation:
    """Set a conversation's title (trimmed, capped to the column width). Empty titles are
    coerced to a sensible default so the sidebar never shows a blank row."""
    clean = (title or "").strip()[:300] or "New conversation"
    conv.title = clean
    await session.flush()
    return conv


async def touch_conversation(session: AsyncSession, conv: Conversation) -> None:
    """Bump ``updated_at`` so the sidebar orders by most-recent activity.

    ``updated_at`` has an ``onupdate`` trigger, but adding a *message* doesn't UPDATE the
    conversation row itself, so it wouldn't fire. Assigning it explicitly forces the write."""
    conv.updated_at = utcnow()
    await session.flush()


def get_summary(conv: Conversation) -> tuple[str, int]:
    """Return the stored rolling summary and how many messages it already covers.

    Stored in ``conversation.meta`` (a JSON column) to avoid a dedicated column. ``upto`` is
    the message count summarized so far, so the packer knows which recent messages remain."""
    meta = conv.meta or {}
    return str(meta.get("summary", "") or ""), int(meta.get("summary_upto", 0) or 0)


async def set_summary(session: AsyncSession, conv: Conversation, summary: str, upto: int) -> None:
    """Persist the rolling summary. Reassigns ``meta`` (rather than mutating in place) so
    SQLAlchemy detects the change on the JSON column."""
    conv.meta = {**(conv.meta or {}), "summary": summary, "summary_upto": int(upto)}
    await session.flush()
