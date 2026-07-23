import json
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, QueueName
from sk_shared.constants import RedisNS
from sk_shared.models.auth import User
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.payment import Installment, Loan, PaymentMethod, PaymentTransaction
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.core.audit import record_audit_event
from src.core.dependencies import get_current_user, get_db, get_redis
from src.api.v1.internal import _orders_for_down_payment_txn
from src.services.notify import notify
from src.schemas.payments import (
    DownPaymentRequest,
    DownPaymentResponse,
    InstallmentDetail,
    PaymentMethodCreateRequest,
    PaymentMethodResponse,
    PaymentScheduleResponse,
    VcnIssueRequest,
    VcnIssueResponse,
)

router = APIRouter(prefix="/payments", tags=["payments"])
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


def _idempotency_cache_key(user_id: int, scope: str, idempotency_key: str) -> str:
    return f"{RedisNS.PAYMENT_IDEMPOTENT}:{scope}:{user_id}:{idempotency_key}"


async def _idempotency_get_cached(
    redis: RedisClient,
    user_id: int,
    scope: str,
    idempotency_key: str | None,
) -> DownPaymentResponse | None:
    if not idempotency_key:
        return None
    cached = await redis.get(_idempotency_cache_key(user_id, scope, idempotency_key))
    if not cached:
        return None
    try:
        payload = json.loads(cached)
        return DownPaymentResponse(**payload)
    except Exception:
        return None


async def _idempotency_set_cached(
    redis: RedisClient,
    user_id: int,
    scope: str,
    idempotency_key: str | None,
    response: DownPaymentResponse,
) -> None:
    if not idempotency_key:
        return
    await redis.set(
        _idempotency_cache_key(user_id, scope, idempotency_key),
        response.model_dump_json(),
        IDEMPOTENCY_TTL_SECONDS,
    )


class InstallmentPayBody(BaseModel):
    method: str = Field(..., pattern="^(safepay|jazzcash|easypaisa|raast)$")
    amount_pkr: Decimal = Field(..., gt=0)


class InstallmentPayRequest(InstallmentPayBody):
    installment_id: int = Field(..., gt=0)


async def _submit_installment_payment(
    installment_id: int,
    method: str,
    amount_pkr: Decimal,
    request: Request,
    current_user: User,
    db: AsyncSession,
    redis: RedisClient,
    idempotency_key: str | None = None,
) -> DownPaymentResponse:
    cached = await _idempotency_get_cached(
        redis,
        current_user.id,
        f"installment:{installment_id}",
        idempotency_key,
    )
    if cached is not None:
        return cached

    installment = await db.scalar(
        select(Installment).where(
            Installment.id == installment_id,
            Installment.user_id == current_user.id,
            Installment.deleted_at.is_(None),
        )
    )
    if installment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSTALLMENT_NOT_FOUND")
    if installment.status == "paid":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="INSTALLMENT_ALREADY_PAID")

    loan = await db.scalar(select(Loan).where(Loan.id == installment.loan_id, Loan.user_id == current_user.id))
    if loan is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INSTALLMENT_NOT_OWNED")

    # TASK-10: Validate that amount matches expected installment amount (tolerance: 1 PKR)
    expected_amount = float(installment.total_amount)
    if abs(float(amount_pkr) - expected_amount) > 1.0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INSTALLMENT_AMOUNT_MISMATCH")

    payment = PaymentTransaction(
        user_id=current_user.id,
        order_id=loan.order_id,
        loan_id=loan.id,
        installment_id=installment.id,
        amount=float(amount_pkr),
        gateway=method,
        transaction_type="installment_repayment",
        provider=method,
        status="initiated",
    )
    db.add(payment)

    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="payments",
        action="installment_payment_initiated",
        target_id=installment.id,
        changes={"installment_id": installment_id, "amount_pkr": str(amount_pkr), "method": method},
    )

    await db.commit()
    await db.refresh(payment)

    payment_job = json.dumps({
        "event": "payment.installment_requested",
        "payment_id": payment.id,
        "installment_id": installment.id,
        "loan_id": loan.id,
        "user_id": current_user.id,
        "amount": float(amount_pkr),
        "gateway": method,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    })
    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.PAYMENT_INITIATE, payment_job)

    # DEV ONLY: see create_down_payment — no real gateway webhook will ever
    # arrive locally, so mark the installment paid immediately.
    if settings.ENVIRONMENT != "production":
        payment.status = "confirmed"
        installment.status = "paid"
        installment.paid_amount = float(amount_pkr)
        installment.paid_at = datetime.now(timezone.utc)
        loan.total_paid = float(loan.total_paid or 0) + float(amount_pkr)
        loan.total_outstanding = max(float(loan.total_outstanding or 0) - float(amount_pkr), 0.0)
        await notify(
            db, current_user.id, "payment",
            f"Installment #{installment.installment_number} received",
            f"Your payment of PKR {amount_pkr:,.0f} via {method} has been received. Outstanding balance: PKR {loan.total_outstanding:,.0f}.",
            source_event="payment.installment_paid", source_reference=f"loan:{loan.id}",
        )
        await db.commit()
        await db.refresh(payment)

    response = DownPaymentResponse(
        payment_id=payment.id,
        status=payment.status,
        transaction_id=getattr(payment, "gateway_txn_id", None),
        checkout_url=None,
    )
    await _idempotency_set_cached(
        redis,
        current_user.id,
        f"installment:{installment_id}",
        idempotency_key,
        response,
    )
    return response


@router.post("/vcn/issue", response_model=VcnIssueResponse)
async def issue_vcn(
    req: VcnIssueRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    order = await db.scalar(
        select(Order).where(
            Order.id == req.order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    if order.status not in (OrderState.DOWN_PAYMENT_RECEIVED,):
        if order.status == OrderState.CONTRACTS_SIGNED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="DOWN_PAYMENT_NOT_CONFIRMED",
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="VCN_GATE_NOT_PASSED")
        
    old_status = order.status
    order.status = "pending_vcn"
    db.add(OrderStatusHistory(
        order_id=order.id, 
        from_status=old_status,
        to_status="pending_vcn", 
        reason="vcn_issue_requested",
    ))
    # We delay committing until end of logic normally, but here audit expects to log the action.

    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="payments",
        action="vcn_issue_requested",
        target_id=order.id,
        changes={"order_id": order.id},
    )

    vcn_job = json.dumps({
        "event": "vcn.issue_requested",
        "order_id": order.id,
        "user_id": current_user.id,
        "amount": float(order.total_amount),
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    })
    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.VCN_ISSUE, vcn_job)

    await db.commit()

    # DEV ONLY: no payment-orchestrator (VCN issuance) or product-service checkout
    # bot is running locally to consume the queued jobs above. Simulate their
    # combined effect — card issuance, automated purchase, and shipment dispatch —
    # so the post-payment order-tracking flow is observable end-to-end without
    # those services. Production behavior (queue-and-wait) is untouched.
    if settings.ENVIRONMENT != "production":
        await _dev_simulate_fulfillment(db, order)

    return VcnIssueResponse(status="queued", order_id=order.id)


async def _dev_simulate_fulfillment(db: AsyncSession, order: Order) -> None:
    from datetime import timedelta
    from sk_shared.models.payment import VirtualCard
    from sk_shared.models.delivery import Shipment, TrackingEvent

    now = datetime.now(timezone.utc)
    card = VirtualCard(
        order_id=order.id,
        user_id=order.user_id,
        issuer="stripe",
        issuer_card_id=f"dev-vcn-{order.id}-{int(now.timestamp())}",
        masked_number="4242" + "*" * 8 + "4242",
        card_expiry=(now + timedelta(days=365)).date(),
        authorized_amount=float(order.total_amount),
        loaded_amount=float(order.total_amount),
        status="used",
        is_used=True,
        used_at=now,
        charged_amount=float(order.total_amount),
        issued_at=now,
        expires_at=now + timedelta(days=90),
    )
    db.add(card)

    order.status = OrderState.PURCHASE_CONFIRMED
    db.add(OrderStatusHistory(order_id=order.id, from_status=OrderState.VCN_ISSUED, to_status=OrderState.PURCHASE_CONFIRMED, reason="dev_auto_checkout_bot"))

    order.status = OrderState.DELIVERY_PENDING
    db.add(OrderStatusHistory(order_id=order.id, from_status=OrderState.PURCHASE_CONFIRMED, to_status=OrderState.DELIVERY_PENDING, reason="dev_auto_shipment_dispatched"))

    shipment = Shipment(
        order_id=order.id,
        courier_name="BlueEx Logistics",
        tracking_number=f"DEV-TRK-{order.id}-{int(now.timestamp())}",
        status="in_transit",
        estimated_delivery=(now + timedelta(days=3)).date(),
    )
    db.add(shipment)
    await db.flush()

    db.add(TrackingEvent(
        shipment_id=shipment.id,
        event_code="picked_up",
        event_description="Package picked up from merchant warehouse",
        location_city="Karachi",
        event_time=now.replace(tzinfo=None),  # event_time is a naive partition key column
    ))

    await notify(
        db, order.user_id, "delivery",
        "Your order has shipped",
        f"Tracking number {shipment.tracking_number} via {shipment.courier_name}. Estimated delivery in 3 days.",
        source_event="delivery.shipped", source_reference=f"order:{order.id}",
    )

    await db.commit()


@router.post("/down-payment", response_model=DownPaymentResponse)
async def create_down_payment(
    req: DownPaymentRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    cached = await _idempotency_get_cached(
        redis,
        current_user.id,
        f"down_payment:{req.order_id}",
        idempotency_key,
    )
    if cached is not None:
        return cached

    # Lock order row to make duplicate down-payment initiation race-safe.
    order = await db.scalar(
        select(Order).where(
            Order.id == req.order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        ).with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    if order.status != OrderState.CONTRACTS_SIGNED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CONTRACTS_NOT_SIGNED")

    # Cart orders share one Loan for unified financing — pass any of the cart's
    # order_ids and this resolves to the SAME combined down payment amount and
    # pays for the whole group in one transaction. order.loan_id is only set once
    # every order sharing this order's cart has signed its own Murabaha contract.
    loan = None
    if order.loan_id is not None:
        loan = await db.scalar(select(Loan).where(Loan.id == order.loan_id))
        if loan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LOAN_NOT_FOUND")
        expected = float(loan.down_payment_amount or 0)
    else:
        from sk_shared.models.cart import CartItem

        cart_item = await db.scalar(select(CartItem).where(CartItem.order_id == order.id))
        if cart_item is not None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CART_CONTRACTS_NOT_FULLY_SIGNED")
        expected = float(order.down_payment_amount or 0)

    if abs(float(req.amount_pkr) - expected) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DOWN_PAYMENT_AMOUNT_MISMATCH")

    # Check for existing pending payment transactions (prevent duplicates). For cart
    # orders this must be scoped to the shared loan, not just this one order_id,
    # since any sibling order_id can be used to pay the group's down payment.
    existing_txn_query = select(PaymentTransaction).where(
        PaymentTransaction.transaction_type == "down_payment",
        PaymentTransaction.status.in_(["initiated", "pending"]),
        PaymentTransaction.deleted_at.is_(None),
    )
    if loan is not None:
        existing_txn_query = existing_txn_query.where(PaymentTransaction.loan_id == loan.id)
    else:
        existing_txn_query = existing_txn_query.where(PaymentTransaction.order_id == order.id)
    existing_txn = await db.scalar(existing_txn_query)
    if existing_txn:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DOWN_PAYMENT_ALREADY_INITIATED")

    # BUG-01 FIX: Do NOT change order status here. Order stays in CONTRACTS_SIGNED.
    # Status will be updated only when payment is confirmed in payment_confirmed_callback

    payment = PaymentTransaction(
        user_id=current_user.id,
        order_id=order.id,
        loan_id=loan.id if loan is not None else None,
        amount=float(req.amount_pkr),
        gateway=req.method,
        transaction_type="down_payment",
        provider=req.method,
        status="initiated",
    )
    db.add(payment)
    # Don't commit yet to avoid split transaction with audit trail
    
    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="payments",
        action="down_payment_initiated",
        target_id=order.id,
        changes={
            "order_id": order.id,
            "amount_pkr": str(req.amount_pkr),
            "method": req.method,
        },
    )
    
    await db.commit()
    await db.refresh(payment)
    
    payment_job = json.dumps({
        "event": "payment.initiate_requested",
        "payment_id": payment.id,
        "order_id": order.id,
        "user_id": current_user.id,
        "amount": float(req.amount_pkr),
        "gateway": req.method,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    })
    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.PAYMENT_INITIATE, payment_job)

    # DEV ONLY: no real payment gateway (JazzCash/Safepay/Raast) is configured in
    # local/dev environments, so the webhook that would normally confirm this
    # transaction will never arrive. Auto-confirm immediately so the down-payment
    # -> VCN issuance -> checkout flow is observable end-to-end without live
    # gateway credentials. Production is untouched — it still waits for the real
    # webhook to hit payment_confirmed_callback.
    if settings.ENVIRONMENT != "production":
        payment.status = "confirmed"
        for sibling_order in await _orders_for_down_payment_txn(db, payment):
            if sibling_order.status == OrderState.CONTRACTS_SIGNED:
                sibling_order.status = OrderState.DOWN_PAYMENT_RECEIVED
                db.add(OrderStatusHistory(
                    order_id=sibling_order.id,
                    from_status=OrderState.CONTRACTS_SIGNED,
                    to_status=OrderState.DOWN_PAYMENT_RECEIVED,
                    reason="down_payment_confirmed_dev_auto",
                ))
        await notify(
            db, current_user.id, "payment",
            "Down payment received",
            f"Your down payment of PKR {req.amount_pkr:,.0f} via {req.method} has been confirmed.",
            source_event="payment.down_payment_confirmed", source_reference=f"order:{order.id}",
        )
        await db.commit()
        await db.refresh(payment)

    response = DownPaymentResponse(
        payment_id=payment.id,
        status=payment.status,
        transaction_id=getattr(payment, "gateway_txn_id", None),
        checkout_url=None, # Will be set by webhook or orchestrator
    )
    await _idempotency_set_cached(
        redis,
        current_user.id,
        f"down_payment:{req.order_id}",
        idempotency_key,
        response,
    )
    return response


@router.get("/schedule/{order_id}", response_model=PaymentScheduleResponse)
async def get_payment_schedule(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Resolve via order.loan_id first so any order in a cart's unified-financing
    # group resolves to the same shared Loan, not just the "primary" order that
    # loans.order_id happens to point at.
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    loan = None
    if order is not None and order.loan_id is not None:
        loan = await db.scalar(select(Loan).where(Loan.id == order.loan_id, Loan.user_id == current_user.id))
    if loan is None:
        loan = await db.scalar(
            select(Loan).where(
                Loan.order_id == order_id,
                Loan.user_id == current_user.id,
                Loan.deleted_at.is_(None),
            )
        )
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LOAN_NOT_FOUND")

    installments = (
        await db.execute(
            select(Installment).where(
                Installment.loan_id == loan.id,
                Installment.deleted_at.is_(None),
            ).order_by(Installment.installment_number.asc())
        )
    ).scalars().all()

    return PaymentScheduleResponse(
        loan_id=loan.id,
        loan_number=loan.loan_number,
        total_amount=loan.total_repayable,
        installments=[
            InstallmentDetail(
                id=i.id,
                number=i.installment_number,
                due_date=i.due_date,
                amount=i.total_amount,
                status=i.status,
                paid_at=i.paid_at,
            )
            for i in installments
        ],
    )


@router.post("/installment/{installment_id}/pay", response_model=DownPaymentResponse)
async def pay_installment(
    installment_id: int,
    payload: InstallmentPayBody,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    return await _submit_installment_payment(
        installment_id=installment_id,
        method=payload.method,
        amount_pkr=payload.amount_pkr,
        request=request,
        current_user=current_user,
        db=db,
        redis=redis,
        idempotency_key=idempotency_key,
    )


@router.post("/installment/pay", response_model=DownPaymentResponse)
async def pay_installment_legacy(
    payload: InstallmentPayRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    return await _submit_installment_payment(
        installment_id=payload.installment_id,
        method=payload.method,
        amount_pkr=payload.amount_pkr,
        request=request,
        current_user=current_user,
        db=db,
        redis=redis,
        idempotency_key=idempotency_key,
    )


# ============================================================================
# TASK-24: VCN Status Endpoint
# ============================================================================

@router.get("/vcn/status/{order_id}")
async def vcn_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Endpoint for customers to check VCN issuance status"""
    from sk_shared.models.payment import VirtualCard
    
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    
    vcn = await db.scalar(
        select(VirtualCard).where(
            VirtualCard.order_id == order_id,
            VirtualCard.deleted_at.is_(None),
        )
    )
    
    if not vcn:
        return {
            "order_id": order_id,
            "vcn_status": "not_issued",
            "order_status": order.status,
        }
    
    return {
        "order_id": order_id,
        "vcn_status": getattr(vcn, "status", "unknown"),
        "masked_number": getattr(vcn, "masked_number", None),
        "expiry_month": getattr(vcn, "expiry_month", None),
        "expiry_year": getattr(vcn, "expiry_year", None),
        "order_status": order.status,
    }


class RefundRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


@router.post("/installment/retry", response_model=DownPaymentResponse)
async def retry_failed_installment(
    payload: InstallmentPayRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    return await _submit_installment_payment(
        installment_id=payload.installment_id,
        method=payload.method,
        amount_pkr=payload.amount_pkr,
        request=request,
        current_user=current_user,
        db=db,
        redis=redis,
        idempotency_key=idempotency_key,
    )


@router.post("/refund/{order_id}")
async def request_customer_refund(
    order_id: int,
    payload: RefundRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id, 
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None)
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    refundable_statuses = {
        "purchase_confirmed",
        "delivery_pending",
        "completed",
    }
    if str(order.status) not in refundable_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ORDER_NOT_REFUNDABLE_BY_CUSTOMER",
        )

    if hasattr(redis, "redis"):
        event = {
            "event": "payment.refund_requested",
            "order_id": order.id,
            "user_id": current_user.id,
            "amount": float(order.total_amount or 0),
            "reason": f"customer_requested: {payload.reason}",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        await redis.redis.lpush(QueueName.PAYMENT_INITIATE, json.dumps(event))

    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="payments",
        action="customer_refund_requested",
        target_id=order.id,
        changes={
            "reason": payload.reason,
            "amount": float(order.total_amount or 0),
        },
    )
    await db.commit()
    return {"order_id": order.id, "status": "refund_requested", "queued": True}


# ============================================================================
# Saved Payment Methods
# ============================================================================

def _mask_identifier(identifier: str, method_type: str) -> str:
    cleaned = identifier.strip()
    if method_type == "wallet":
        return cleaned[:4] + "*" * max(len(cleaned) - 7, 3) + cleaned[-3:] if len(cleaned) > 7 else cleaned
    return cleaned[:4] + "*" * max(len(cleaned) - 8, 4) + cleaned[-4:] if len(cleaned) > 8 else cleaned


@router.get("/methods", response_model=list[PaymentMethodResponse])
async def list_payment_methods(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    methods = (
        await db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == current_user.id, PaymentMethod.deleted_at.is_(None))
            .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
        )
    ).scalars().all()
    return [PaymentMethodResponse.model_validate(m) for m in methods]


@router.post("/methods", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
async def add_payment_method(
    payload: PaymentMethodCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid

    existing_count = await db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.user_id == current_user.id, PaymentMethod.deleted_at.is_(None)
        )
    )

    method = PaymentMethod(
        user_id=current_user.id,
        provider=payload.provider,
        method_type=payload.method_type,
        # DEV ONLY: no real payment gateway tokenizes this locally, so we mint a
        # placeholder tokenized reference instead of round-tripping to JazzCash/
        # Safepay/etc. Production would store the real gateway-issued token here.
        tokenized_reference=f"dev_tok_{_uuid.uuid4().hex}",
        masked_pan=_mask_identifier(payload.account_identifier, payload.method_type),
        expiry_month=payload.expiry_month,
        expiry_year=payload.expiry_year,
        is_default=existing_count is None,
    )
    db.add(method)
    await db.commit()
    await db.refresh(method)
    return PaymentMethodResponse.model_validate(method)


@router.delete("/methods/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_payment_method(
    method_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    method = await db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == method_id,
            PaymentMethod.user_id == current_user.id,
            PaymentMethod.deleted_at.is_(None),
        )
    )
    if method is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAYMENT_METHOD_NOT_FOUND")

    method.deleted_at = datetime.now(timezone.utc)
    was_default = method.is_default
    method.is_default = False
    await db.flush()

    if was_default:
        next_method = await db.scalar(
            select(PaymentMethod).where(
                PaymentMethod.user_id == current_user.id, PaymentMethod.deleted_at.is_(None)
            ).order_by(PaymentMethod.created_at.desc())
        )
        if next_method is not None:
            next_method.is_default = True

    await db.commit()
    return


@router.post("/methods/{method_id}/default", response_model=PaymentMethodResponse)
async def set_default_payment_method(
    method_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    method = await db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == method_id,
            PaymentMethod.user_id == current_user.id,
            PaymentMethod.deleted_at.is_(None),
        )
    )
    if method is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PAYMENT_METHOD_NOT_FOUND")

    others = (
        await db.execute(
            select(PaymentMethod).where(
                PaymentMethod.user_id == current_user.id,
                PaymentMethod.id != method_id,
                PaymentMethod.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for other in others:
        other.is_default = False
    method.is_default = True

    await db.commit()
    await db.refresh(method)
    return PaymentMethodResponse.model_validate(method)
