"""Model registry operations + resolution of public ids/aliases to upstream models."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.model import Model


async def resolve_model(session: AsyncSession, public_id: str) -> Model | None:
    """Resolve a customer-supplied model id or alias to a registry entry."""
    # Exact public_id match first.
    result = await session.execute(select(Model).where(Model.public_id == public_id))
    model = result.scalar_one_or_none()
    if model is not None:
        return model
    # Alias match (aliases stored as JSON list; scan enabled models).
    result = await session.execute(select(Model).where(Model.enabled.is_(True)))
    for candidate in result.scalars().all():
        if public_id in (candidate.aliases or []):
            return candidate
    return None


async def get_default_model(session: AsyncSession) -> Model | None:
    result = await session.execute(select(Model).where(Model.is_default.is_(True)).limit(1))
    model = result.scalar_one_or_none()
    if model:
        return model
    result = await session.execute(select(Model).where(Model.enabled.is_(True)).limit(1))
    return result.scalar_one_or_none()


async def list_models(session: AsyncSession, *, enabled_only: bool = False) -> list[Model]:
    stmt = select(Model).order_by(Model.public_id)
    if enabled_only:
        stmt = stmt.where(Model.enabled.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_model_or_404(session: AsyncSession, model_id: str) -> Model:
    model = await session.get(Model, model_id)
    if model is None:
        raise NotFoundError("Model not found.")
    return model


async def create_model(session: AsyncSession, **fields) -> Model:
    if fields.get("is_default"):
        await _clear_default(session)
    model = Model(**fields)
    session.add(model)
    await session.flush()
    return model


async def update_model(session: AsyncSession, model: Model, **fields) -> Model:
    if fields.get("is_default"):
        await _clear_default(session)
    for key, value in fields.items():
        if value is not None:
            setattr(model, key, value)
    await session.flush()
    return model


async def _clear_default(session: AsyncSession) -> None:
    result = await session.execute(select(Model).where(Model.is_default.is_(True)))
    for m in result.scalars().all():
        m.is_default = False
