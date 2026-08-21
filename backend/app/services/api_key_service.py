"""API key lifecycle: create, list, revoke, rotate, and lookup for auth."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_api_key
from app.errors import NotFoundError
from app.logging_config import get_logger
from app.models.api_key import ApiKey
from app.models.enums import DEFAULT_SCOPES, SCOPES, KeyStatus
from app.models.user import User
from app.utils.ids import key_prefix, raw_api_key
from app.utils.time import utcnow

logger = get_logger("app.services.api_key")

# Hidden per-user key backing the first-party chat product (see ApiKey.is_system). It is
# never displayed or returned as a raw secret, and is granted every consumer scope so the
# session-authed chat surface can reuse the full /v1 pipeline. The chat-product gates live
# above chat_service.prepare — this key is NOT a way to bypass them.
SYSTEM_KEY_NAME = "Chat (system)"
SYSTEM_KEY_SCOPES = sorted(SCOPES)


async def create_api_key(
    session: AsyncSession,
    *,
    user_id: str,
    name: str = "Default key",
    project_id: str | None = None,
    scopes: list[str] | None = None,
    expires_in_days: int | None = None,
    rpm_limit: int | None = None,
    tpm_limit: int | None = None,
) -> tuple[ApiKey, str]:
    raw = raw_api_key(live=True)
    valid_scopes = [s for s in (scopes or DEFAULT_SCOPES) if s in SCOPES] or list(DEFAULT_SCOPES)
    expires_at = utcnow() + timedelta(days=expires_in_days) if expires_in_days else None

    key = ApiKey(
        name=name,
        key_prefix=key_prefix(raw),
        key_hash=hash_api_key(raw),
        user_id=user_id,
        project_id=project_id,
        scopes=valid_scopes,
        status=KeyStatus.ACTIVE,
        expires_at=expires_at,
        rpm_limit=rpm_limit,
        tpm_limit=tpm_limit,
    )
    session.add(key)
    await session.flush()
    logger.info("api_key_created", extra={"api_key_id": key.id, "user_id": user_id})
    return key, raw


async def list_api_keys(
    session: AsyncSession, *, user_id: str | None = None, include_system: bool = False
) -> list[ApiKey]:
    stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
    if user_id:
        stmt = stmt.where(ApiKey.user_id == user_id)
    if not include_system:
        # The hidden chat system key must never appear in any account/admin listing.
        stmt = stmt.where(ApiKey.is_system.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_key_or_404(
    session: AsyncSession, key_id: str, *, user_id: str | None = None, include_system: bool = False
) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if key is None or (user_id is not None and key.user_id != user_id):
        raise NotFoundError("API key not found.")
    if key.is_system and not include_system:
        # System keys are unmanageable through the public key surface: revoking or rotating
        # one would silently break the owner's chat. Treat as not-found so no endpoint can
        # target it. (get_or_create_system_key re-activates it if it ever gets disabled.)
        raise NotFoundError("API key not found.")
    return key


async def get_or_create_system_key(session: AsyncSession, user_id: str) -> ApiKey:
    """Return the caller's hidden chat system key, provisioning it on first use.

    Idempotent: one ``is_system`` key per user. The raw secret is generated to derive the
    stored hash/prefix and then discarded — it is never returned, so this key can only be
    used internally via :func:`app.dependencies.build_context_for_key`, never presented to
    ``/v1``. The organization is stamped from the user so quota/usage accounting attributes
    to the right org, exactly like a normal key. If a prior key was somehow disabled/expired,
    it is reactivated rather than duplicated."""
    existing = (
        await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.is_system.is_(True))
        )
    ).scalars().first()
    if existing is not None:
        if existing.status != KeyStatus.ACTIVE:
            existing.status = KeyStatus.ACTIVE
            existing.revoked_at = None
            existing.expires_at = None
            await session.flush()
        return existing

    user = await session.get(User, user_id)
    raw = raw_api_key(live=True)
    key = ApiKey(
        name=SYSTEM_KEY_NAME,
        key_prefix=key_prefix(raw),
        key_hash=hash_api_key(raw),
        user_id=user_id,
        organization_id=user.primary_org_id if user is not None else None,
        scopes=list(SYSTEM_KEY_SCOPES),
        status=KeyStatus.ACTIVE,
        is_system=True,
    )
    session.add(key)
    await session.flush()
    logger.info("system_key_provisioned", extra={"api_key_id": key.id, "user_id": user_id})
    return key


async def revoke_api_key(session: AsyncSession, key: ApiKey) -> ApiKey:
    key.status = KeyStatus.REVOKED
    key.revoked_at = utcnow()
    await session.flush()
    logger.info("api_key_revoked", extra={"api_key_id": key.id})
    return key


async def rotate_api_key(session: AsyncSession, key: ApiKey) -> tuple[ApiKey, str]:
    """Revoke the existing secret and issue a fresh one on the same key record."""
    raw = raw_api_key(live=True)
    key.key_prefix = key_prefix(raw)
    key.key_hash = hash_api_key(raw)
    key.status = KeyStatus.ACTIVE
    key.revoked_at = None
    await session.flush()
    logger.info("api_key_rotated", extra={"api_key_id": key.id})
    return key, raw


async def lookup_by_raw(session: AsyncSession, raw: str) -> ApiKey | None:
    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))
    return result.scalar_one_or_none()


async def touch_last_used(session: AsyncSession, key: ApiKey) -> None:
    key.last_used_at = utcnow()
    await session.flush()
