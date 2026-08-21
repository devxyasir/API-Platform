"""OpenAI-compatible Models endpoint (/v1/models)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import AuthContext, require_scope
from app.errors import NotFoundError
from app.schemas.openai import ModelList, ModelObject
from app.services import model_service

router = APIRouter(tags=["Models"])


@router.get("/models", response_model=ModelList, summary="List available models")
async def list_models(
    ctx: AuthContext = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_session),
):
    models = await model_service.list_models(session, enabled_only=True)
    allowed = set(ctx.project.allowed_models) if ctx.project and ctx.project.allowed_models else None
    data = [
        ModelObject(id=m.public_id, created=int(m.created_at.timestamp()), owned_by=m.provider)
        for m in models
        if allowed is None or m.public_id in allowed
    ]
    return ModelList(data=data)


@router.get("/models/{model_id}", response_model=ModelObject, summary="Retrieve a model")
async def retrieve_model(
    model_id: str,
    ctx: AuthContext = Depends(require_scope("models:read")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.resolve_model(session, model_id)
    if model is None or not model.enabled:
        raise NotFoundError(f"The model '{model_id}' does not exist.", code="model_not_found")
    return ModelObject(id=model.public_id, created=int(model.created_at.timestamp()), owned_by=model.provider)
