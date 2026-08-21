"""Admin API-key moderation (platform-wide).

The admin control-plane view of **every** account's API keys, for support/abuse handling:
list (optionally filtered to one user), inspect, revoke and delete. Requires an
admin-scoped session and the ``keys.*`` RBAC permission — a user-scoped token is rejected.

Key *creation* and *rotation* mint a secret and are self-service only (``/account/api-keys``);
they are intentionally absent here so an admin cannot silently issue a usable secret under
another account. Admins manage their own keys through the same self-service surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.models.user import User
from app.schemas.api_key import ApiKeyOut
from app.schemas.common import OK
from app.services import api_key_service, audit_service

router = APIRouter(tags=["API Keys"], prefix="/api-keys")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("", response_model=list[ApiKeyOut], summary="List API keys (all accounts)")
async def list_keys(
    user_id: str | None = Query(default=None, description="Filter to a single account."),
    _admin: User = Depends(require_permission("keys.read")),
    session: AsyncSession = Depends(get_session),
):
    keys = await api_key_service.list_api_keys(session, user_id=user_id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.get("/{key_id}", response_model=ApiKeyOut, summary="Get any API key")
async def get_key(
    key_id: str,
    _admin: User = Depends(require_permission("keys.read")),
    session: AsyncSession = Depends(get_session),
):
    key = await api_key_service.get_key_or_404(session, key_id, user_id=None)
    return ApiKeyOut.model_validate(key)


@router.post("/{key_id}/revoke", response_model=ApiKeyOut, summary="Revoke any API key")
async def revoke_key(
    key_id: str,
    request: Request,
    admin: User = Depends(require_permission("keys.write")),
    session: AsyncSession = Depends(get_session),
):
    key = await api_key_service.get_key_or_404(session, key_id, user_id=None)
    key = await api_key_service.revoke_api_key(session, key)
    await audit_service.record_audit(
        session, action="api_key.revoked", actor_id=admin.id, actor_email=admin.email,
        target_type="api_key", target_id=key.id, meta={"owner_id": key.user_id}, ip_hash=_ip(request),
    )
    return ApiKeyOut.model_validate(key)


@router.delete("/{key_id}", response_model=OK, summary="Delete any API key")
async def delete_key(
    key_id: str,
    request: Request,
    admin: User = Depends(require_permission("keys.write")),
    session: AsyncSession = Depends(get_session),
):
    key = await api_key_service.get_key_or_404(session, key_id, user_id=None)
    owner_id = key.user_id
    await session.delete(key)
    await session.flush()
    await audit_service.record_audit(
        session, action="api_key.deleted", actor_id=admin.id, actor_email=admin.email,
        target_type="api_key", target_id=key_id, meta={"owner_id": owner_id}, ip_hash=_ip(request),
    )
    return OK(detail="API key deleted.")
