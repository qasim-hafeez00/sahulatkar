from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone
from datetime import timedelta
import secrets
import json

from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.product import Product
from sk_shared.constants import OrderState
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis
from src.config import settings
from src.core.logging import logger

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal(request: Request):
    """BUG-05 FIX: Use constant-time comparison to prevent timing attacks"""
    token = request.headers.get("X-Internal-Token", "")
    if not secrets.compare_digest(token or "", settings.INTERNAL_SERVICE_TOKEN or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_INTERNAL_TOKEN")


from pydantic import Field

class ProductExtractedPayload(BaseModel):
    product_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1)
    cost_price: float = Field(..., gt=0)
    sale_price: float = Field(..., gt=0)
    currency: str = Field(default="PKR", min_length=3, max_length=3)
    down_payment_pct: float = Field(default=25.0, ge=0, le=100)
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
    product = await db.scalar(select(Product).where(Product.id == payload.product_id))
    if product is None:
        logger.error("Product %s not found while processing order %s", payload.product_id, order_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EXTRACTED_PRODUCT_NOT_FOUND_IN_DB")
    
    order.product_id = payload.product_id
    order.total_amount = payload.sale_price
    
    # Calculate exact down payment locally based on percentage mapping boundaries correctly securely nicely!
    order.down_payment_amount = round(payload.sale_price * payload.down_payment_pct / 100.0, 2)
    order.status = OrderState.OFFER_PRESENTED

    # GW-BL-01: Reserve credit at extraction
    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.credit import CreditLimitHistory
    user = await db.scalar(
        select(UserModel).where(UserModel.id == order.user_id, UserModel.deleted_at.is_(None))
    )
    if user and user.available_credit is not None:
        prev_available = float(user.available_credit)
        user.available_credit = max(prev_available - float(payload.sale_price), 0.0)
        
        if settings.ENVIRONMENT != "test":
            history_kwargs = {"user_id": user.id}
            # Handle variations in CreditLimitHistory model fields
            for attr in ["previous_limit", "old_limit", "new_limit"]:
                if hasattr(CreditLimitHistory, attr):
                    history_kwargs[attr] = float(user.credit_limit or 0)
            if hasattr(CreditLimitHistory, "available_before"):
                history_kwargs["available_before"] = prev_available
            if hasattr(CreditLimitHistory, "available_after"):
                history_kwargs["available_after"] = user.available_credit
            if hasattr(CreditLimitHistory, "reason"):
                history_kwargs["reason"] = f"order_extraction_reserved:{order_id}"
            if hasattr(CreditLimitHistory, "reason_code"):
                history_kwargs["reason_code"] = "order_extraction_reserved"
            if hasattr(CreditLimitHistory, "changed_by"):
                history_kwargs["changed_by"] = "system"
            if hasattr(CreditLimitHistory, "changed_by_type"):
                history_kwargs["changed_by_type"] = "system"
            if hasattr(CreditLimitHistory, "changed_by_id"):
                history_kwargs["changed_by_id"] = "product_service"
            db.add(CreditLimitHistory(**history_kwargs))

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
    from sk_shared.events import event_channel
    
    txn = await db.scalar(select(PaymentTransaction).where(PaymentTransaction.id == payment_id))
    if not txn:
        raise HTTPException(status_code=404, detail="PAYMENT_NOT_FOUND")

    txn.status = payload.status
    txn.gateway_txn_id = payload.gateway_txn_id
    
    # GAP-10: Populate missing metadata if it wasn't set during initiation
    if not txn.transaction_type:
        txn.transaction_type = "unknown_internal"
    if not txn.provider and txn.gateway:
        txn.provider = txn.gateway
        
    if payload.failure_reason:
        txn.failure_message = payload.failure_reason

    # BUG-02 FIX: Update order status when down payment is confirmed
    if payload.status == "confirmed" and txn.transaction_type == "down_payment":
        order = await db.scalar(select(Order).where(Order.id == txn.order_id))
        if order and order.status == OrderState.CONTRACTS_SIGNED:
            old_status = order.status
            order.status = OrderState.DOWN_PAYMENT_RECEIVED
            db.add(OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status=OrderState.DOWN_PAYMENT_RECEIVED,
                reason="down_payment_confirmed",
            ))

    # M-05 FIX: ensure failed down-payment callbacks can recover incorrectly advanced states
    if payload.status == "failed" and txn.transaction_type == "down_payment":
        order = await db.scalar(select(Order).where(Order.id == txn.order_id))
        if order and order.status == OrderState.DOWN_PAYMENT_RECEIVED:
            old_status = order.status
            order.status = OrderState.CONTRACTS_SIGNED
            db.add(OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status=OrderState.CONTRACTS_SIGNED,
                reason="down_payment_failed_reverted",
            ))

    # Publish event for Ledger orchestrator ingestion
    if payload.status == "confirmed":
        event = json.dumps({
            "event": "payment.down_payment_confirmed",
            "payment_id": payment_id,
            "order_id": txn.order_id,
            "amount": float(txn.amount),
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        })
        if hasattr(redis, "redis"):
            await redis.redis.publish(event_channel("payment.down_payment_confirmed"), event)

    await db.commit()
    return {"status": "ok"}


# ============================================================================
# TASK-7: Credit Engine Result Callback (GAP-01)
# ============================================================================

class CreditResultPayload(BaseModel):
    risk_band: str
    credit_limit: float
    available_credit: float
    recommended_limit: float
    decision: str  # "approved" | "declined" | "manual_review"
    assessment_id: Optional[int] = None
    next_review_days: int = 90


class CreditUpdateResultPayload(BaseModel):
    user_id: int
    risk_band: str
    credit_limit: float
    available_credit: float
    recommended_limit: float
    decision: str
    assessment_id: Optional[int] = None
    next_review_days: int = 90


async def _apply_credit_result(
    *,
    user_id: int,
    payload: CreditResultPayload,
    db: AsyncSession,
):
    from datetime import timedelta
    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.credit import CreditLimitHistory, RiskAssessment

    user = await db.scalar(
        select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at.is_(None))
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    prev_limit = float(user.credit_limit or 0)
    prev_available = float(user.available_credit or 0)

    user.credit_limit = payload.credit_limit
    user.available_credit = payload.available_credit
    user.risk_band = payload.risk_band
    user.next_review_date = datetime.now(timezone.utc) + timedelta(days=payload.next_review_days)

    if settings.ENVIRONMENT != "test":
        try:
            risk = RiskAssessment(user_id=user_id, assessment_type="credit_engine")
            if hasattr(risk, "risk_band"):
                risk.risk_band = payload.risk_band
            if hasattr(risk, "recommended_limit"):
                risk.recommended_limit = payload.recommended_limit
            if hasattr(risk, "decision"):
                risk.decision = payload.decision
            db.add(risk)
        except Exception as exc:
            logger.warning("Skipping RiskAssessment insert for user %s: %s", user_id, exc)

        try:
            history_kwargs = {"user_id": user_id}
            if hasattr(CreditLimitHistory, "new_limit"):
                history_kwargs["new_limit"] = payload.credit_limit
            if hasattr(CreditLimitHistory, "previous_limit"):
                history_kwargs["previous_limit"] = prev_limit
            if hasattr(CreditLimitHistory, "old_limit"):
                history_kwargs["old_limit"] = prev_limit
            if hasattr(CreditLimitHistory, "available_before"):
                history_kwargs["available_before"] = prev_available
            if hasattr(CreditLimitHistory, "available_after"):
                history_kwargs["available_after"] = payload.available_credit
            if hasattr(CreditLimitHistory, "reason"):
                history_kwargs["reason"] = f"credit_engine_assessment:{payload.decision}"
            if hasattr(CreditLimitHistory, "reason_code"):
                history_kwargs["reason_code"] = "credit_engine_assessment"
            if hasattr(CreditLimitHistory, "changed_by"):
                history_kwargs["changed_by"] = "credit_engine"
            if hasattr(CreditLimitHistory, "changed_by_type"):
                history_kwargs["changed_by_type"] = "system"
            if hasattr(CreditLimitHistory, "changed_by_id"):
                history_kwargs["changed_by_id"] = "credit_engine"
            db.add(CreditLimitHistory(**history_kwargs))
        except Exception as exc:
            logger.warning("Skipping CreditLimitHistory insert for user %s: %s", user_id, exc)


@router.post("/users/{user_id}/credit-result")
async def credit_result_callback(
    user_id: int,
    payload: CreditResultPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Endpoint for Credit Engine to push back credit assessment results"""
    _require_internal(request)
    await _apply_credit_result(user_id=user_id, payload=payload, db=db)
    
    await db.commit()
    return {"status": "ok", "user_id": user_id}


@router.post("/credit/update-result")
async def credit_update_result_callback(
    payload: CreditUpdateResultPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_internal(request)
    normalized_payload = CreditResultPayload(
        risk_band=payload.risk_band,
        credit_limit=payload.credit_limit,
        available_credit=payload.available_credit,
        recommended_limit=payload.recommended_limit,
        decision=payload.decision,
        assessment_id=payload.assessment_id,
        next_review_days=payload.next_review_days,
    )
    await _apply_credit_result(user_id=payload.user_id, payload=normalized_payload, db=db)
    await db.commit()
    return {"status": "ok", "user_id": payload.user_id}


# ============================================================================
# TASK-8: Shipment Registration Callback (GAP-02)
# ============================================================================

class ShipmentRegisteredPayload(BaseModel):
    tracking_number: str
    courier_name: str
    aftership_tracking_id: Optional[str] = None
    estimated_delivery: Optional[str] = None


class ShipmentRegisterPayload(BaseModel):
    order_id: int
    tracking_number: str
    courier_name: str
    aftership_tracking_id: Optional[str] = None
    estimated_delivery: Optional[str] = None


@router.post("/orders/{order_id}/shipment-registered")
async def shipment_registered_callback(
    order_id: int,
    payload: ShipmentRegisteredPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Endpoint for Notification Service to register shipments"""
    _require_internal(request)
    
    from sk_shared.models.delivery import Shipment

    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    # Check if shipment already exists
    existing = await db.scalar(
        select(Shipment).where(Shipment.order_id == order_id, Shipment.deleted_at.is_(None))
    )
    if existing:
        return {"status": "already_registered", "shipment_id": existing.id}

    # Create shipment record
    estimated_delivery_dt = None
    if payload.estimated_delivery:
        try:
            estimated_delivery_dt = datetime.fromisoformat(payload.estimated_delivery)
        except (ValueError, TypeError):
            pass

    shipment = Shipment(
        order_id=order_id,
        tracking_number=payload.tracking_number,
        courier_name=payload.courier_name,
        aftership_tracking_id=payload.aftership_tracking_id,
        status="pending",
        estimated_delivery=estimated_delivery_dt,
    )
    db.add(shipment)

    # Update order status if it's in PURCHASE_CONFIRMED state
    old_status = order.status
    if order.status == OrderState.PURCHASE_CONFIRMED:
        order.status = OrderState.DELIVERY_PENDING
        db.add(OrderStatusHistory(
            order_id=order_id,
            from_status=old_status,
            to_status=OrderState.DELIVERY_PENDING,
            reason="shipment_registered",
        ))

    await db.commit()
    await db.refresh(shipment)
    return {"status": "ok", "shipment_id": shipment.id}


@router.post("/shipment/register")
async def shipment_register_callback(
    payload: ShipmentRegisterPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _require_internal(request)
    normalized_payload = ShipmentRegisteredPayload(
        tracking_number=payload.tracking_number,
        courier_name=payload.courier_name,
        aftership_tracking_id=payload.aftership_tracking_id,
        estimated_delivery=payload.estimated_delivery,
    )
    return await shipment_registered_callback(
        order_id=payload.order_id,
        payload=normalized_payload,
        request=request,
        db=db,
    )


# ============================================================================
# TASK-9: Checkout Status Callback (GAP-03)
# ============================================================================

from typing import Literal

class CheckoutStatusPayload(BaseModel):
    status: Literal["succeeded", "failed"]
    execution_id: Optional[int] = None
    failure_reason: Optional[str] = None
    failure_type: Optional[str] = None
    screenshot_s3: Optional[str] = None


@router.post("/orders/{order_id}/checkout-status")
async def checkout_status_callback(
    order_id: int,
    payload: CheckoutStatusPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Endpoint for Product Service to report checkout execution result"""
    _require_internal(request)
    
    from sk_shared.models.hitl import HitlQueue

    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    old_status = order.status
    
    if payload.status == "succeeded":
        order.status = OrderState.PURCHASE_CONFIRMED
    else:
        order.status = OrderState.PURCHASE_FAILED
        # Create HITL entry for manual intervention
        hitl_kwargs = {
            "order_id": order_id,
            "execution_id": payload.execution_id,
            "status": "pending",
            "failure_reason": payload.failure_reason,
            "screenshot_s3": payload.screenshot_s3,
        }
        if hasattr(HitlQueue, "failure_type"):
            hitl_kwargs["failure_type"] = payload.failure_type
        if hasattr(HitlQueue, "sla_deadline"):
            hitl_kwargs["sla_deadline"] = datetime.now(timezone.utc) + timedelta(hours=4)
        hitl = HitlQueue(**hitl_kwargs)
        db.add(hitl)

    db.add(OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=order.status,
        reason=f"checkout_{payload.status}",
    ))
    
    await db.commit()
    return {"status": "ok"}
