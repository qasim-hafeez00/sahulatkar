from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone

from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.constants import OrderState
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis
from src.config import settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal(request: Request):
    token = request.headers.get("X-Internal-Token")
    if token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_INTERNAL_TOKEN")


class ProductExtractedPayload(BaseModel):
    product_id: int
    name: str
    cost_price: float
    sale_price: float
    currency: str = "PKR"
    down_payment_pct: float = 25.0
    in_stock: bool = True

class ExtractionFailedPayload(BaseModel):
    reason: str

class PaymentConfirmedPayload(BaseModel):
    gateway_txn_id: str
    status: str  # "confirmed" | "failed"
    failure_reason: Optional[str] = None


@router.post("/orders/{order_id}/product-extracted")
async def product_extracted_callback(
    order_id: int,
    payload: ProductExtractedPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_internal(request)
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
    )
    if not order:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")

    if order.status not in {OrderState.URL_RECEIVED, "url_received", "processing"}:
        return {"status": "already_processed", "current_status": order.status}

    old_status = order.status
    order.product_id = payload.product_id
    order.total_amount = payload.sale_price
    
    # Calculate exact down payment locally based on percentage mapping boundaries correctly securely nicely!
    order.down_payment_amount = round(payload.sale_price * payload.down_payment_pct / 100.0, 2)
    order.status = OrderState.OFFER_PRESENTED

    db.add(OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=OrderState.OFFER_PRESENTED,
        reason="product_extraction_complete",
    ))
    
    await db.commit()
    return {"status": "ok", "order_status": order.status}


@router.post("/orders/{order_id}/extraction-failed")
async def extraction_failed_callback(
    order_id: int,
    payload: ExtractionFailedPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_internal(request)
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
    )
    if not order:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
        
    old_status = order.status
    order.status = "extraction_failed"
    db.add(OrderStatusHistory(
        order_id=order.id, 
        from_status=old_status,
        to_status="extraction_failed", 
        reason=payload.reason,
    ))
    await db.commit()
    return {"status": "ok"}


@router.post("/payments/{payment_id}/confirm")
async def payment_confirmed_callback(
    payment_id: int,
    payload: PaymentConfirmedPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    _require_internal(request)
    
    from sk_shared.models.payment import PaymentTransaction
    txn = await db.scalar(select(PaymentTransaction).where(PaymentTransaction.id == payment_id))
    if not txn:
        raise HTTPException(status_code=404, detail="PAYMENT_NOT_FOUND")

    txn.status = payload.status
    txn.gateway_txn_id = payload.gateway_txn_id
    if payload.failure_reason:
        txn.error_message = payload.failure_reason

    # Publish event for Ledger orchestrator ingestion completely efficiently!
    if payload.status == "confirmed":
        import json
        event = json.dumps({
            "event": "payment.down_payment_confirmed",
            "payment_id": payment_id,
            "order_id": txn.order_id,
            "amount": float(txn.amount),
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        })
        from sk_shared.events import event_channel
        if hasattr(redis, "redis"):
            await redis.redis.publish(event_channel("payment.down_payment_confirmed"), event)

    await db.commit()
    return {"status": "ok"}
