"""Invoice & billing-simulation administration (§30-34).

No real payment provider is contacted. Invoices are generated from the price snapshots
already recorded on each usage row, so historical billing never re-prices with today's
rates (§53). See ``billing_service`` for the ``BillingProvider`` abstraction."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.errors import InvalidRequestError
from app.models.user import User
from app.schemas.admin import InvoiceGenerate, InvoiceOut
from app.schemas.common import Page
from app.services import audit_service, billing_service, organization_service

router = APIRouter(tags=["Billing"], prefix="/billing")


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get("/invoices", response_model=Page[InvoiceOut], summary="List invoices")
async def list_invoices(
    organization_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("billing.read")),
    session: AsyncSession = Depends(get_session),
):
    rows, total = await billing_service.list_invoices(
        session, organization_id=organization_id, status=status, limit=limit, offset=offset
    )
    return Page[InvoiceOut](
        items=[InvoiceOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut, summary="Get an invoice")
async def get_invoice(
    invoice_id: str,
    _admin: User = Depends(require_permission("billing.read")),
    session: AsyncSession = Depends(get_session),
):
    inv = await billing_service.get_invoice_or_404(session, invoice_id)
    return InvoiceOut.model_validate(inv)


@router.post(
    "/invoices/generate",
    response_model=InvoiceOut,
    status_code=201,
    summary="Generate an invoice for a period (billing sim)",
)
async def generate_invoice(
    body: InvoiceGenerate,
    request: Request,
    admin: User = Depends(require_permission("billing.write")),
    session: AsyncSession = Depends(get_session),
):
    if body.period_end <= body.period_start:
        raise InvalidRequestError("period_end must be after period_start.", code="invalid_period")
    await organization_service.get_org_or_404(session, body.organization_id)
    inv = await billing_service.generate_invoice(
        session, organization_id=body.organization_id,
        period_start=body.period_start, period_end=body.period_end,
        subscription_id=body.subscription_id, plan_fee_usd=body.plan_fee_usd,
    )
    await audit_service.record_audit(
        session, action="invoice.generated", actor_id=admin.id, actor_email=admin.email,
        target_type="invoice", target_id=inv.id,
        meta={"organization_id": body.organization_id, "number": inv.number,
              "total_usd": inv.total_usd}, ip_hash=_ip(request),
    )
    return InvoiceOut.model_validate(inv)


@router.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceOut, summary="Mark an invoice paid")
async def mark_paid(
    invoice_id: str,
    request: Request,
    admin: User = Depends(require_permission("billing.write")),
    session: AsyncSession = Depends(get_session),
):
    inv = await billing_service.get_invoice_or_404(session, invoice_id)
    inv = await billing_service.mark_paid(session, inv)
    await audit_service.record_audit(
        session, action="invoice.marked_paid", actor_id=admin.id, actor_email=admin.email,
        target_type="invoice", target_id=inv.id, meta={"number": inv.number}, ip_hash=_ip(request),
    )
    return InvoiceOut.model_validate(inv)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceOut, summary="Void an invoice")
async def void_invoice(
    invoice_id: str,
    request: Request,
    admin: User = Depends(require_permission("billing.write")),
    session: AsyncSession = Depends(get_session),
):
    inv = await billing_service.get_invoice_or_404(session, invoice_id)
    inv = await billing_service.void_invoice(session, inv)
    await audit_service.record_audit(
        session, action="invoice.voided", actor_id=admin.id, actor_email=admin.email,
        target_type="invoice", target_id=inv.id, meta={"number": inv.number}, ip_hash=_ip(request),
    )
    return InvoiceOut.model_validate(inv)
