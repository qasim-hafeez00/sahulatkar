from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import VirtualCard

from src.core.dependencies import get_db, get_redis
from src.schemas.vcn import VcnIssueRequest, VcnIssueResponse, VcnStatusResponse
from src.services.vcn import VcnService

router = APIRouter(prefix="/payments", tags=["vcn"])


@router.post("/vcn/issue", response_model=VcnIssueResponse)
async def issue_vcn(
    request_payload: VcnIssueRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    service = VcnService(db, get_redis(request))
    card = await service.issue_vcn(
        order_id=request_payload.order_id,
        amount_pkr=request_payload.amount_pkr,
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
async def void_vcn(vcn_id: int, reason: str = "manual_void", db: AsyncSession = Depends(get_db)):
    card = await db.scalar(select(VirtualCard).where(VirtualCard.id == vcn_id, VirtualCard.deleted_at.is_(None)))
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCN_NOT_FOUND")
    card.status = "voided"
    card.void_reason = reason
    await db.commit()
    return {"status": "voided", "vcn_id": vcn_id}


@router.get("/vcn/{order_id}/status", response_model=VcnStatusResponse)
async def vcn_status(order_id: int, db: AsyncSession = Depends(get_db)):
    card = await db.scalar(select(VirtualCard).where(VirtualCard.order_id == order_id, VirtualCard.deleted_at.is_(None)))
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCN_NOT_FOUND")
    return VcnStatusResponse(
        status=card.status,
        charged_amount=float(card.charged_amount),
        is_used=card.is_used,
        issued_at=card.issued_at,
        expires_at=card.expires_at,
    )