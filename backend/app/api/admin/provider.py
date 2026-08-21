"""Upstream provider status and configuration (administrators only).

The live upstream credential lives in environment configuration and is used only
inside the provider adapter. This endpoint exposes a *masked* view and the health
snapshot; it never returns the real secret.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_admin
from app.errors import NotFoundError
from app.models.provider_config import ProviderConfig
from app.models.user import User
from app.providers import registry
from app.schemas.admin import ProviderOut, ProviderUpdate
from app.services import audit_service
from app.utils.time import utcnow

router = APIRouter(tags=["Provider"], prefix="/provider")


@router.get("", response_model=list[ProviderOut], summary="List provider configurations")
async def list_providers(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ProviderConfig).order_by(ProviderConfig.name))
    return [ProviderOut.model_validate(p) for p in result.scalars().all()]


@router.get("/status", summary="Live circuit-breaker status")
async def provider_status(_admin: User = Depends(require_admin)):
    return [
        {
            "provider": name,
            "circuit_state": registry.breaker(name).state,
            "consecutive_failures": registry.breaker(name).failures,
        }
        for name in registry.provider_names
    ]


@router.patch("/{provider_id}", response_model=ProviderOut, summary="Update provider settings")
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    provider = await session.get(ProviderConfig, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found.")
    # Only non-secret settings are editable here; secrets come from the environment.
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(provider, key, value)
    await session.flush()
    await audit_service.record_audit(
        session, action="provider.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="provider", target_id=provider.id,
        ip_hash=getattr(request.state, "ip_hash", None),
    )
    return ProviderOut.model_validate(provider)


@router.post("/{provider_id}/health-check", summary="Probe the upstream provider")
async def health_check(
    provider_id: str,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    provider = await session.get(ProviderConfig, provider_id)
    if provider is None:
        raise NotFoundError("Provider not found.")

    adapter = registry.get(provider.provider_type or "openai")
    ok, latency = await adapter.health_check()

    provider.last_status = "healthy" if ok else "unhealthy"
    provider.last_latency_ms = latency
    provider.last_checked_at = utcnow()
    await session.flush()

    return {
        "provider": provider.name,
        "healthy": ok,
        "latency_ms": round(latency, 2) if latency is not None else None,
        "checked_at": provider.last_checked_at.isoformat(),
    }
