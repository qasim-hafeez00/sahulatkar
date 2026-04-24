"""
VCN API endpoints.

External endpoints (JWT auth):
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

from src.core.dependencies import get_db, get_redis, require_internal_token
from src.core.metrics import VCN_VOID_TOTAL
from src.schemas.vcn import VcnDecryptResponse, VcnIssueRequest, VcnIssueResponse, VcnStatusResponse
from src.services.vcn import VcnService
from decimal import Decimal

router = APIRouter(prefix="/payments", tags=["vcn"])


@router.post("/vcn/issue", response_model=VcnIssueResponse)
async def issue_vcn(
    request_payload: VcnIssueRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Issue a VCN for an order. Requires CONTRACTS_SIGNED state."""
    service = VcnService(db, get_redis(request))
    card = await service.issue_vcn(
        order_id=request_payload.order_id,
        amount_pkr=Decimal(str(request_payload.amount_pkr)),
        merchant_domain=request_payload.merchant_domain,
    )
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


@router.post("/vcn/{vcn_id}/void")
async def void_vcn(
    vcn_id: int,
    reason: str = "manual_void",
    db: AsyncSession = Depends(get_db),
):
    """Void a VCN. Blocked VCN cannot be re-activated."""
    card = await db.scalar(
        select(VirtualCard).where(VirtualCard.id == vcn_id, VirtualCard.deleted_at.is_(None))
    )
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCN_NOT_FOUND")
    if card.status == "voided":
        return {"status": "already_voided", "vcn_id": vcn_id}

    card.status = "voided"
    card.void_reason = reason
    await db.commit()

    VCN_VOID_TOTAL.labels(reason=reason).inc()
    return {"status": "voided", "vcn_id": vcn_id, "reason": reason}


@router.get("/vcn/{order_id}/status", response_model=VcnStatusResponse)
async def vcn_status(order_id: int, db: AsyncSession = Depends(get_db)):
    """Get VCN status for a given order."""
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


@router.get("/internal/vcn/{order_id}/decrypt", response_model=VcnDecryptResponse)
async def internal_decrypt_vcn(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_token),
):
    """
    INTERNAL ONLY — Decrypt and return plaintext PAN/CVV for the checkout agent.

    This endpoint is NEVER called by the customer frontend.
    Only the Product Service (checkout agent) calls this with X-Internal-Token.
    The response must NOT be logged in full at INFO level.
    """
    service = VcnService(db, get_redis(request))
    result = await service.decrypt_vcn(order_id)
    return VcnDecryptResponse(**result)