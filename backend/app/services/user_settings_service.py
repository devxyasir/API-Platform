"""Per-user chat settings (custom instructions, personalization + memory toggles).

One row per user, created lazily. Kept deliberately small: it only shapes how the
first-party chat assistant responds and what long-term context it may use — never
account/billing state (those are admin-controlled elsewhere).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings

# Fields a user is allowed to change about their own chat experience. Anything not in
# this set is ignored on update, so a stray/hostile key can never write an arbitrary column.
_EDITABLE = {
    "custom_instructions_about",
    "custom_instructions_style",
    "preferred_model",
    "memory_enabled",
    "personalization_enabled",
}

# Guard rails so a huge paste can't blow up the prompt budget on every turn.
_MAX_INSTRUCTION_CHARS = 4000


async def get_or_create(session: AsyncSession, user_id: str) -> UserSettings:
    """Return the caller's settings row, creating a default one on first access."""
    row = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def update(session: AsyncSession, user_id: str, changes: dict) -> UserSettings:
    """Apply a partial update (``exclude_unset`` dict from the schema). Only whitelisted
    fields are written; text fields are trimmed and capped; ``preferred_model`` normalizes
    an empty string to ``None`` (server default)."""
    row = await get_or_create(session, user_id)
    for key, value in changes.items():
        if key not in _EDITABLE:
            continue
        if key in ("custom_instructions_about", "custom_instructions_style"):
            value = (value or "").strip()[:_MAX_INSTRUCTION_CHARS]
        elif key == "preferred_model":
            value = (value or "").strip() or None
        setattr(row, key, value)
    await session.flush()
    return row
