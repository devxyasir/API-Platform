"""Model registry & price administration (§53).

Models map a public id/alias to a real upstream model; prices are versioned snapshots so
historical billing always uses the rate in effect at request time (never today's)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.models.user import User
from app.schemas.admin import ModelCreate, ModelOut, ModelPriceOut, ModelPriceSet, ModelUpdate
from app.schemas.common import OK
from app.services import audit_service, model_service, pricing_service

router = APIRouter(tags=["Models"], prefix="/models")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("", response_model=list[ModelOut], summary="List all models")
async def list_models(
    _admin: User = Depends(require_permission("models.read")),
    session: AsyncSession = Depends(get_session),
):
    models = await model_service.list_models(session)
    return [ModelOut.model_validate(m) for m in models]


@router.post("", response_model=ModelOut, status_code=201, summary="Register a model")
async def create_model(
    body: ModelCreate,
    request: Request,
    admin: User = Depends(require_permission("models.write")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.create_model(session, **body.model_dump())
    await audit_service.record_audit(
        session, action="model.created", actor_id=admin.id, actor_email=admin.email,
        target_type="model", target_id=model.id, ip_hash=_ip(request),
    )
    return ModelOut.model_validate(model)


# --- prices (§53) ------------------------------------------------------------
@router.get("/prices", response_model=list[ModelPriceOut], summary="Current model prices")
async def current_prices(
    _admin: User = Depends(require_permission("models.read")),
    session: AsyncSession = Depends(get_session),
):
    rows = await pricing_service.current_prices(session)
    return [ModelPriceOut.model_validate(r) for r in rows]


@router.get("/{model_id}", response_model=ModelOut, summary="Get a model")
async def get_model(
    model_id: str,
    _admin: User = Depends(require_permission("models.read")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.get_model_or_404(session, model_id)
    return ModelOut.model_validate(model)


@router.get(
    "/{model_id}/prices",
    response_model=list[ModelPriceOut],
    summary="Price history for a model",
)
async def price_history(
    model_id: str,
    _admin: User = Depends(require_permission("models.read")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.get_model_or_404(session, model_id)
    rows = await pricing_service.price_history(session, model.public_id)
    return [ModelPriceOut.model_validate(r) for r in rows]


@router.put(
    "/{model_id}/prices",
    response_model=ModelPriceOut,
    summary="Set a model's price (opens a new snapshot)",
)
async def set_price(
    model_id: str,
    body: ModelPriceSet,
    request: Request,
    admin: User = Depends(require_permission("models.write")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.get_model_or_404(session, model_id)
    row = await pricing_service.set_price(
        session, model_public_id=model.public_id,
        input_price_per_1m=body.input_price_per_1m,
        output_price_per_1m=body.output_price_per_1m, created_by=admin.id,
    )
    await audit_service.record_audit(
        session, action="model.price_set", actor_id=admin.id, actor_email=admin.email,
        target_type="model", target_id=model.id,
        meta={"model": model.public_id, "input_price_per_1m": body.input_price_per_1m,
              "output_price_per_1m": body.output_price_per_1m}, ip_hash=_ip(request),
    )
    return ModelPriceOut.model_validate(row)


@router.patch("/{model_id}", response_model=ModelOut, summary="Update a model")
async def update_model(
    model_id: str,
    body: ModelUpdate,
    request: Request,
    admin: User = Depends(require_permission("models.write")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.get_model_or_404(session, model_id)
    model = await model_service.update_model(session, model, **body.model_dump(exclude_unset=True))
    await audit_service.record_audit(
        session, action="model.updated", actor_id=admin.id, actor_email=admin.email,
        target_type="model", target_id=model.id, ip_hash=_ip(request),
    )
    return ModelOut.model_validate(model)


@router.delete("/{model_id}", response_model=OK, summary="Delete a model")
async def delete_model(
    model_id: str,
    request: Request,
    admin: User = Depends(require_permission("models.write")),
    session: AsyncSession = Depends(get_session),
):
    model = await model_service.get_model_or_404(session, model_id)
    await session.delete(model)
    await session.flush()
    await audit_service.record_audit(
        session, action="model.deleted", actor_id=admin.id, actor_email=admin.email,
        target_type="model", target_id=model_id, ip_hash=_ip(request),
    )
    return OK(detail="Model deleted.")
