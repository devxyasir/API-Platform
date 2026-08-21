"""Your API keys (``/account/api-keys``).

Strictly self-scoped: every lookup is constrained to ``user_id == caller`` so one account
can never see, rotate or revoke another account's key. The raw secret is returned exactly
once, at creation/rotation. (Admins manage all keys via ``/admin/api-keys``.)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.schemas.common import OK
from app.services import api_key_service, audit_service

router = APIRouter(tags=["Account API Keys"], prefix="/api-keys")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("", response_model=list[ApiKeyOut], summary="List your API keys")
async def list_keys(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    keys = await api_key_service.list_api_keys(session, user_id=user.id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreatedOut, status_code=201, summary="Create an API key")
async def create_key(
    body: ApiKeyCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    key, raw = await api_key_service.create_api_key(
        session, user_id=user.id, name=body.name, project_id=body.project_id,
        scopes=body.scopes, expires_in_days=body.expires_in_days,
        rpm_limit=body.rpm_limit, tpm_limit=body.tpm_limit,
    )
    await audit_service.record_audit(
        session, action="api_key.created", actor_id=user.id, actor_email=user.email,
        target_type="api_key", target_id=key.id, ip_hash=_ip(request),
    )
    out = ApiKeyOut.model_validate(key).model_dump()
    return ApiKeyCreatedOut(**out, key=raw)


@router.post("/{key_id}/revoke", response_model=ApiKeyOut, summary="Revoke one of your API keys")
async def revoke_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    key = await api_key_service.get_key_or_404(session, key_id, user_id=user.id)
    key = await api_key_service.revoke_api_key(session, key)
    await audit_service.record_audit(
        session, action="api_key.revoked", actor_id=user.id, actor_email=user.email,
        target_type="api_key", target_id=key.id, ip_hash=_ip(request),
    )
    return ApiKeyOut.model_validate(key)


@router.post("/{key_id}/rotate", response_model=ApiKeyCreatedOut, summary="Rotate one of your API keys")
async def rotate_key(
    key_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    key = await api_key_service.get_key_or_404(session, key_id, user_id=user.id)
    key, raw = await api_key_service.rotate_api_key(session, key)
    await audit_service.record_audit(
        session, action="api_key.rotated", actor_id=user.id, actor_email=user.email,
        target_type="api_key", target_id=key.id, ip_hash=_ip(request),
    )
    out = ApiKeyOut.model_validate(key).model_dump()
    return ApiKeyCreatedOut(**out, key=raw)


@router.delete("/{key_id}", response_model=OK, summary="Delete one of your API keys")
async def delete_key(
    key_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    key = await api_key_service.get_key_or_404(session, key_id, user_id=user.id)
    await session.delete(key)
    await session.flush()
    return OK(detail="API key deleted.")
