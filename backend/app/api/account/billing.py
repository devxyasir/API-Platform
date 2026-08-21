"""Your billing (``/account/billing``).

Read-only views of the caller's own organization: current subscription, credit balance
and ledger, invoices, and the catalogue of public plans (for upgrade comparison). All
billing *mutations* — granting credits, generating invoices, changing plans — are admin
actions under ``/admin/*`` and a simulated billing lifecycle; a user cannot alter their
own balance or subscription here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.account.deps import get_account_org
from app.database import get_session
from app.dependencies import get_current_user
from app.errors import NotFoundError
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.user import User
from app.schemas.admin import (
    CreditBalanceOut,
    CreditTransactionOut,
    InvoiceOut,
    PlanOut,
    SubscriptionOut,
)
from app.schemas.common import Page
from app.services import (
    billing_service,
    credit_service,
    plan_service,
    subscription_service,
)

router = APIRouter(tags=["Account Billing"], prefix="/billing")


async def _plan_out(session: AsyncSession, plan: Plan) -> PlanOut:
    """Fold a plan's limit/feature/model rows into a single public response object."""
    return PlanOut(
        id=plan.id, slug=plan.slug, name=plan.name, description=plan.description,
        active=plan.active, archived=plan.archived, is_public=plan.is_public,
        price_monthly_usd=plan.price_monthly_usd, price_yearly_usd=plan.price_yearly_usd,
        monthly_credits=plan.monthly_credits, trial_days=plan.trial_days,
        sort_order=plan.sort_order, created_at=plan.created_at,
        limits=await plan_service.limit_map(session, plan.id),
        features=await plan_service.feature_map(session, plan.id),
        models=await plan_service.allowed_models(session, plan.id),
    )


@router.get("/subscription", response_model=SubscriptionOut | None, summary="Your current subscription")
async def subscription(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    sub = await subscription_service.get_active_subscription(session, org.id)
    if sub is None:
        return None
    out = SubscriptionOut.model_validate(sub)
    plan = await session.get(Plan, sub.plan_id)
    if plan is not None:
        out.plan_slug = plan.slug
        out.plan_name = plan.name
    return out


@router.get("/credits", response_model=CreditBalanceOut, summary="Your credit balance")
async def credit_balance(
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    balance = await credit_service.get_balance(session, org.id)
    return CreditBalanceOut(organization_id=org.id, balance=balance)


@router.get("/credits/ledger", response_model=Page[CreditTransactionOut], summary="Your credit history")
async def credit_ledger(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    rows, total = await credit_service.ledger(session, org.id, limit=limit, offset=offset)
    return Page[CreditTransactionOut](
        items=[CreditTransactionOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/invoices", response_model=Page[InvoiceOut], summary="Your invoices")
async def invoices(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    rows, total = await billing_service.list_invoices(
        session, organization_id=org.id, status=status, limit=limit, offset=offset
    )
    return Page[InvoiceOut](
        items=[InvoiceOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut, summary="Get one of your invoices")
async def get_invoice(
    invoice_id: str,
    org: Organization = Depends(get_account_org),
    session: AsyncSession = Depends(get_session),
):
    invoice = await billing_service.get_invoice_or_404(session, invoice_id)
    # Ownership check: never disclose another organization's invoice.
    if invoice.organization_id != org.id:
        raise NotFoundError("Invoice not found.")
    return InvoiceOut.model_validate(invoice)


@router.get("/plans", response_model=list[PlanOut], summary="Available plans")
async def plans(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
):
    """Public, non-archived plans — the upgrade menu shown to a signed-in user."""
    rows = await plan_service.list_plans(session, include_archived=False, only_public=True)
    return [await _plan_out(session, p) for p in rows]
