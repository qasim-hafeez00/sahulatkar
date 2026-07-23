"""
VCN API endpoints.

External endpoints (JWT auth + order ownership):
  - POST /payments/vcn/issue         — Issue VCN for an order
  - POST /payments/vcn/{id}/void     — Void a VCN
  - GET  /payments/vcn/{order_id}/status — VCN status for an order

Internal-only endpoint (X-Internal-Token):
  - GET  /internal/vcn/{order_id}/decrypt — Return plaintext PAN/CVV for Product Service checkout agent
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import VirtualCard

from src.api.v1.payments import _get_order_for_user
from src.core.dependencies import get_current_user, get_db, get_redis, require_internal_token, rate_limit
from src.core.metrics import VCN_VOID_TOTAL
from src.schemas.vcn import VcnDecryptResponse, VcnIssueRequest, VcnIssueResponse, VcnStatusResponse
from src.services.vcn import VcnService
from decimal import Decimal

router = APIRouter(prefix="/payments", tags=["vcn"])


@router.post("/vcn/issue", response_model=VcnIssueResponse, dependencies=[Depends(rate_limit(5, 60))])
async def issue_vcn(
    request_payload: VcnIssueRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a VCN for an order. Requires CONTRACTS_SIGNED state."""
    await _get_order_for_user(db, request_payload.order_id, current_user.id)
    service = VcnService(db, get_redis(request))
    card = await service.issue_vcn(
        order_id=request_payload.order_id,
        amount_pkr=Decimal(str(request_payload.amount_pkr)),
        merchant_domain=request_payload.merchant_domain,
    )
    await db.commit()
    await db.refresh(card)
    return VcnIssueResponse(
        vcn_id=card.id,
        order_id=card.order_id,
        status=card.status,
        pan=card.masked_number,
        expiry_month=f"{card.card_expiry.month:02d}",
        expiry_year=str(card.card_expiry.year),
        cvv="***",
        issued_at=card.issued_at,
        expires_at=card.expires_at,
    )


@router.post("/vcn/{vcn_id}/void", dependencies=[Depends(rate_limit(10, 60))])
async def void_vcn(
    vcn_id: int,
    reason: str = "manual_void",
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Void a VCN. Blocked VCN cannot be re-activated."""
    card = await db.scalar(
        select(VirtualCard).where(VirtualCard.id == vcn_id, VirtualCard.deleted_at.is_(None))
    )
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCN_NOT_FOUND")
    await _get_order_for_user(db, card.order_id, current_user.id)
    if card.status == "voided":
        return {"status": "already_voided", "vcn_id": vcn_id}

    # GAP-04 + PO-BL-05: Cancel card on Stripe with 3 retries to prevent card staying active.
    import asyncio as _asyncio
    import logging as _log
    from src.adapters.stripe_issuing import StripeIssuingAdapter
    from src.config import settings
    stripe_adapter = StripeIssuingAdapter(
        secret_key=settings.STRIPE_SECRET_KEY,
        fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
        fx_buffer_pct=settings.FX_BUFFER_PCT,
    )
    stripe_cancel_ok = False
    for _attempt in range(3):
        stripe_cancel_ok = stripe_adapter.cancel_card(card.issuer_card_id)
        if stripe_cancel_ok:
            break
        if _attempt < 2:
            await _asyncio.sleep(1)

    if not stripe_cancel_ok:
        _log.getLogger(__name__).error(
            "Stripe card cancellation failed after 3 attempts \u2014 voiding locally only",
            extra={"vcn_id": vcn_id, "issuer_card_id": card.issuer_card_id},
        )

    card.status = "voided"
    card.void_reason = reason
    await db.commit()

    VCN_VOID_TOTAL.labels(reason=reason).inc()
    return {"status": "voided", "vcn_id": vcn_id, "reason": reason, "stripe_canceled": stripe_cancel_ok}


@router.get("/vcn/{order_id}/status", response_model=VcnStatusResponse)
async def vcn_status(
    order_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get VCN status for a given order."""
    await _get_order_for_user(db, order_id, current_user.id)
    card = await db.scalar(
        select(VirtualCard).where(
            VirtualCard.order_id == order_id,
            VirtualCard.deleted_at.is_(None),
        )
    )
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCN_NOT_FOUND")
    return VcnStatusResponse(
        status=card.status,
        charged_amount=float(card.charged_amount),
        is_used=card.is_used,
        issued_at=card.issued_at,
        expires_at=card.expires_at,
    )


@router.get("/internal/vcn/{order_id}/decrypt", response_model=VcnDecryptResponse, dependencies=[Depends(rate_limit(30, 60))])
async def internal_decrypt_vcn(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    """
    INTERNAL ONLY — Decrypt and return plaintext PAN/CVV for the checkout agent.

    PO-BL-01: Rate-limited to 30 req/min to prevent mass PAN exfiltration
    if internal token is compromised.
    This endpoint is NEVER called by the customer frontend.
    Only the Product Service (checkout agent) calls this with X-Internal-Token.
    The response must NOT be logged in full at INFO level.
    """
    service = VcnService(db, get_redis(request))
    result = await service.decrypt_vcn(order_id)
    return VcnDecryptResponse(**result)