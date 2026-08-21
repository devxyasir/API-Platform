"""Credit administration (§14, §58, §59).

The credit ledger (``credit_transactions``) is append-only and the single source of
truth; the org's cached ``credit_balance`` only ever moves alongside a ledger row. A
correction is a new ``adjustment`` row, never an edit of history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import require_permission
from app.models.enums import CreditTxnType
from app.models.user import User
from app.schemas.admin import (
    CreditAdjust,
    CreditBalanceOut,
    CreditGrant,
    CreditRefund,
    CreditTransactionOut,
)
from app.schemas.common import Page
from app.services import audit_service, credit_service, organization_service

router = APIRouter(tags=["Credits"], prefix="/credits")

_GRANT_TYPES = {CreditTxnType.GRANT, CreditTxnType.BONUS, CreditTxnType.PURCHASE}


def _ip(request: Request) -> str | None:
    return getattr(request.state, "ip_hash", None)


@router.get(
    "/{organization_id}/balance",
    response_model=CreditBalanceOut,
    summary="Current credit balance",
)
async def get_balance(
    organization_id: str,
    _admin: User = Depends(require_permission("credits.read")),
    session: AsyncSession = Depends(get_session),
):
    await organization_service.get_org_or_404(session, organization_id)
    balance = await credit_service.get_balance(session, organization_id)
    return CreditBalanceOut(organization_id=organization_id, balance=balance)


@router.get(
    "/{organization_id}/ledger",
    response_model=Page[CreditTransactionOut],
    summary="Credit ledger (append-only)",
)
async def get_ledger(
    organization_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_permission("credits.read")),
    session: AsyncSession = Depends(get_session),
):
    await organization_service.get_org_or_404(session, organization_id)
    rows, total = await credit_service.ledger(session, organization_id, limit=limit, offset=offset)
    return Page[CreditTransactionOut](
        items=[CreditTransactionOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post(
    "/{organization_id}/grant",
    response_model=CreditTransactionOut,
    status_code=201,
    summary="Grant credits",
)
async def grant_credits(
    organization_id: str,
    body: CreditGrant,
    request: Request,
    admin: User = Depends(require_permission("credits.write")),
    session: AsyncSession = Depends(get_session),
):
    org = await organization_service.get_org_or_404(session, organization_id)
    txn_type = body.type if body.type in _GRANT_TYPES else CreditTxnType.GRANT
    txn = await credit_service.grant(
        session, organization_id, body.amount, reason=body.reason, type=txn_type,
        expires_at=body.expires_at, created_by=admin.id, user_id=org.owner_id,
    )
    await audit_service.record_audit(
        session, action="credit.granted", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=organization_id,
        meta={"amount": body.amount, "type": txn_type, "balance_after": txn.balance_after},
        ip_hash=_ip(request),
    )
    return CreditTransactionOut.model_validate(txn)


@router.post(
    "/{organization_id}/adjust",
    response_model=CreditTransactionOut,
    status_code=201,
    summary="Adjust credits (signed correction)",
)
async def adjust_credits(
    organization_id: str,
    body: CreditAdjust,
    request: Request,
    admin: User = Depends(require_permission("credits.write")),
    session: AsyncSession = Depends(get_session),
):
    org = await organization_service.get_org_or_404(session, organization_id)
    txn = await credit_service.adjust(
        session, organization_id, body.delta, reason=body.reason,
        created_by=admin.id, user_id=org.owner_id,
    )
    await audit_service.record_audit(
        session, action="credit.adjusted", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=organization_id,
        meta={"delta": body.delta, "reason": body.reason, "balance_after": txn.balance_after},
        ip_hash=_ip(request),
    )
    return CreditTransactionOut.model_validate(txn)


@router.post(
    "/{organization_id}/refund",
    response_model=CreditTransactionOut,
    status_code=201,
    summary="Refund credits",
)
async def refund_credits(
    organization_id: str,
    body: CreditRefund,
    request: Request,
    admin: User = Depends(require_permission("credits.write")),
    session: AsyncSession = Depends(get_session),
):
    org = await organization_service.get_org_or_404(session, organization_id)
    txn = await credit_service.refund(
        session, organization_id, body.amount, reason=body.reason,
        created_by=admin.id, user_id=org.owner_id,
    )
    await audit_service.record_audit(
        session, action="credit.refunded", actor_id=admin.id, actor_email=admin.email,
        target_type="organization", target_id=organization_id,
        meta={"amount": body.amount, "balance_after": txn.balance_after}, ip_hash=_ip(request),
    )
    return CreditTransactionOut.model_validate(txn)
