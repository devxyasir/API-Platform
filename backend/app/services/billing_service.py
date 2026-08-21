"""Billing simulation (§30-34).

No real payment provider is contacted. A :class:`BillingProvider` abstraction defines
the payment surface so a real processor (e.g. Stripe) can be plugged in later; the
default :class:`ManualBillingProvider` just moves invoices through their lifecycle
locally.

Invoices are generated from the **price snapshots already recorded on each usage row**
at request time (``usage_records.cost_usd``), so historical billing never re-prices with
today's rates (§53). Credits are NOT converted to dollars on the invoice — credits,
tokens, quota and money are kept separate (§58); the credit ledger is the record of
credit movement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import NotFoundError
from app.logging_config import get_logger
from app.models.billing import Invoice
from app.models.enums import InvoiceStatus, SubscriptionStatus
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services import subscription_service, usage_service
from app.utils.time import ensure_aware, utcnow

logger = get_logger("app.services.billing")


# --- provider abstraction ----------------------------------------------------
class BillingProvider(ABC):
    """Payment-surface abstraction. The billing sim only needs the invoice lifecycle;
    a real provider would also create/cancel subscriptions and handle webhooks."""

    name: str = "base"

    @abstractmethod
    async def issue_invoice(self, session: AsyncSession, invoice: Invoice) -> None: ...

    @abstractmethod
    async def collect_invoice(self, session: AsyncSession, invoice: Invoice) -> None: ...


class ManualBillingProvider(BillingProvider):
    """Local, no-op provider: issuing opens the invoice; collection is simulated as an
    immediate success for zero-dollar invoices and left OPEN otherwise (an operator or
    the maintenance loop marks it paid/past_due)."""

    name = "manual"

    async def issue_invoice(self, session: AsyncSession, invoice: Invoice) -> None:
        if invoice.status == InvoiceStatus.DRAFT:
            invoice.status = InvoiceStatus.OPEN
            invoice.issued_at = utcnow()
            await session.flush()

    async def collect_invoice(self, session: AsyncSession, invoice: Invoice) -> None:
        # Nothing to charge for a $0 invoice — mark it paid so it doesn't linger.
        if invoice.total_usd <= 0 and invoice.status in (InvoiceStatus.OPEN, InvoiceStatus.DRAFT):
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = utcnow()
            await session.flush()


_PROVIDERS: dict[str, BillingProvider] = {"manual": ManualBillingProvider()}


def get_provider() -> BillingProvider:
    return _PROVIDERS.get(settings.billing_provider, _PROVIDERS["manual"])


# --- invoice reads -----------------------------------------------------------
async def get_invoice(session: AsyncSession, invoice_id: str) -> Invoice | None:
    return await session.get(Invoice, invoice_id)


async def get_invoice_or_404(session: AsyncSession, invoice_id: str) -> Invoice:
    inv = await get_invoice(session, invoice_id)
    if inv is None:
        raise NotFoundError("Invoice not found.", code="invoice_not_found")
    return inv


async def list_invoices(
    session: AsyncSession,
    *,
    organization_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Invoice], int]:
    conds = []
    if organization_id is not None:
        conds.append(Invoice.organization_id == organization_id)
    if status is not None:
        conds.append(Invoice.status == status)
    total = int(
        (await session.execute(select(func.count()).select_from(Invoice).where(*conds))).scalar() or 0
    )
    rows = (
        await session.execute(
            select(Invoice).where(*conds)
            .order_by(Invoice.period_start.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def _next_invoice_number(session: AsyncSession) -> str:
    count = int((await session.execute(select(func.count()).select_from(Invoice))).scalar() or 0)
    return f"INV-{count + 1:06d}"


# --- invoice generation ------------------------------------------------------
async def generate_invoice(
    session: AsyncSession,
    *,
    organization_id: str,
    period_start: datetime,
    period_end: datetime,
    subscription_id: str | None = None,
    plan_fee_usd: float = 0.0,
    issue: bool = True,
) -> Invoice:
    """Build an invoice for ``[period_start, period_end)`` from the period's usage rows.

    Usage line items come from :func:`usage_service.usage_by_model`, whose ``cost_usd``
    is the sum of the per-request price snapshots — so the invoice reflects the prices
    that were in effect at request time, not today's (§53)."""
    by_model = await usage_service.usage_by_model(
        session, organization_id=organization_id, since=period_start, until=period_end
    )
    usage_usd = round(sum(row["cost_usd"] for row in by_model), 6)

    line_items: list[dict] = []
    if plan_fee_usd:
        line_items.append({
            "description": "Subscription fee",
            "quantity": 1, "unit": "period",
            "amount_usd": round(float(plan_fee_usd), 6),
        })
    for row in by_model:
        line_items.append({
            "description": f"Usage — {row['model']}",
            "quantity": row["total_tokens"], "unit": "token",
            "requests": row["requests"],
            "amount_usd": row["cost_usd"],
        })

    total_usd = round(float(plan_fee_usd) + usage_usd, 6)
    invoice = Invoice(
        organization_id=organization_id,
        subscription_id=subscription_id,
        number=await _next_invoice_number(session),
        status=InvoiceStatus.DRAFT,
        period_start=period_start,
        period_end=period_end,
        plan_fee_usd=round(float(plan_fee_usd), 6),
        usage_usd=usage_usd,
        credits_applied_usd=0.0,  # credits are tracked in the ledger, not as $ here (§58)
        total_usd=total_usd,
        line_items=line_items,
    )
    session.add(invoice)
    await session.flush()

    if issue:
        provider = get_provider()
        await provider.issue_invoice(session, invoice)
        await provider.collect_invoice(session, invoice)
    logger.info("invoice_generated",
                extra={"organization_id": organization_id, "invoice": invoice.number,
                       "total_usd": total_usd, "status": invoice.status})
    return invoice


async def mark_paid(session: AsyncSession, invoice: Invoice) -> Invoice:
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = utcnow()
    await session.flush()
    return invoice


async def void_invoice(session: AsyncSession, invoice: Invoice) -> Invoice:
    invoice.status = InvoiceStatus.VOID
    await session.flush()
    return invoice


# --- maintenance-loop entry point --------------------------------------------
async def run_billing_cycle(session: AsyncSession) -> dict:
    """Roll every subscription whose period has ended and invoice the period that just
    closed (§33). Called by the maintenance scheduler. Never deletes history (§48)."""
    now = utcnow()
    due = (
        await session.execute(
            select(Subscription).where(
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end <= now,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING,
                     SubscriptionStatus.PAST_DUE]
                ),
            )
        )
    ).scalars().all()

    rolled = invoiced = 0
    for sub in due:
        was_trial = sub.status == SubscriptionStatus.TRIALING
        plan = await session.get(Plan, sub.plan_id)
        result = await subscription_service.rollover(session, sub)
        if not result["rolled"]:
            continue
        rolled += 1
        cs, ce = result["closed_period_start"], result["closed_period_end"]
        if cs is None or ce is None:
            continue
        # Trial periods carry no subscription fee; paid plans do.
        fee = 0.0 if was_trial else float(plan.price_monthly_usd if plan else 0.0)
        await generate_invoice(
            session, organization_id=sub.organization_id, subscription_id=sub.id,
            period_start=ensure_aware(cs), period_end=ensure_aware(ce), plan_fee_usd=fee,
        )
        invoiced += 1
    if rolled:
        logger.info("billing_cycle_ran", extra={"rolled": rolled, "invoiced": invoiced})
    return {"rolled": rolled, "invoiced": invoiced}
