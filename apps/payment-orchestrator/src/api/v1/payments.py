"""
Customer-facing payment endpoints.

- POST /payments/down-payment     — Initiate down payment (SafePay redirect or JazzCash/Raast direct)
- POST /payments/pay-installment  — Pay a specific installment
- POST /payments/refund           — Request refund (admin or customer with constraints)
- POST /internal/trigger-installment — Billing sweep trigger (X-Internal-Token required)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.order import Order
from sk_shared.models.payment import Installment, Loan, PaymentMethod, PaymentTransaction, VirtualCard
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.dependencies import get_current_user, get_db, get_redis, require_internal_token
from src.core.metrics import DOWN_PAYMENT_TOTAL, GATEWAY_FAILURE_TOTAL, INSTALLMENT_PAYMENT_TOTAL
from src.schemas.payments import (
    DownPaymentRequest,
    DownPaymentResponse,
    PayInstallmentRequest,
    PayInstallmentResponse,
    RefundRequest,
    RefundResponse,
    WebhookAck,
)
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.refund_service import RefundService
from src.services.routing_engine import GatewayRoutingEngine
from src.services.safepay import SafepayClient
from src.services.vcn import VcnService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

_CALLBACK_BASE = "https://payment-orchestrator.sahulatkar.pk"


async def _get_order_for_user(db: AsyncSession, order_id: int, user_id: int) -> Order:
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == user_id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    return order


@router.post("/down-payment", response_model=DownPaymentResponse)
async def down_payment(
    request_payload: DownPaymentRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Initiate a down payment for a signed order.

    - SafePay: returns a redirect URL; payment confirmed via webhook.
    - JazzCash / Raast: synchronous charge; returns success immediately (mock).
    - Idempotency: if the same idempotency_key is seen again, the existing
      transaction is returned without re-charging.
    """
    # ── Idempotency check ────────────────────────────────────────────────────
    idem_key = f"sk:payment:idem:{request_payload.idempotency_key}"
    existing_txn_id = await redis.get(idem_key)
    if existing_txn_id:
        existing_txn = await db.scalar(
            select(PaymentTransaction).where(PaymentTransaction.id == int(existing_txn_id))
        )
        if existing_txn:
            return DownPaymentResponse(
                status=existing_txn.status,
                order_id=request_payload.order_id,
                payment_transaction_id=existing_txn.id,
                gateway_txn_id=existing_txn.gateway_txn_id,
                idempotency_key=request_payload.idempotency_key,
            )

    order = await _get_order_for_user(db, request_payload.order_id, current_user.id)

    if order.status != OrderState.CONTRACTS_SIGNED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MURABAHA_NOT_SIGNED",
        )

    # ── Down payment range validation ────────────────────────────────────────
    total_amount = Decimal(str(order.total_amount))
    min_amount = (total_amount * (settings.DOWN_PAYMENT_MIN_PCT / Decimal("100"))).quantize(Decimal("0.01"))
    max_amount = (total_amount * (settings.DOWN_PAYMENT_MAX_PCT / Decimal("100"))).quantize(Decimal("0.01"))

    if not (min_amount <= request_payload.amount_pkr <= max_amount):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"DOWN_PAYMENT_OUT_OF_RANGE: must be {min_amount}–{max_amount} PKR",
        )

    service = VcnService(db, redis)
    routing = GatewayRoutingEngine(redis)
    method = request_payload.method.value

    # ── SafePay: redirect flow ────────────────────────────────────────────────
    if method == "safepay":
        try:
            safepay = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, settings.SAFEPAY_BASE_URL)
            checkout = safepay.create_checkout(
                order_id=order.id,
                amount_pkr=request_payload.amount_pkr,
                callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/safepay",
            )
        except Exception as exc:
            await routing.record_failure("safepay")
            GATEWAY_FAILURE_TOTAL.labels(gateway="safepay").inc()
            logger.error("SafePay checkout creation failed", extra={"order_id": order.id, "error": str(exc)})
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GATEWAY_ERROR") from exc

        txn = PaymentTransaction(
            user_id=current_user.id,
            amount=request_payload.amount_pkr,
            currency=settings.PAYMENT_CURRENCY,
            gateway="safepay",
            gateway_txn_id=checkout.gateway_txn_id,
            gateway_response=checkout.payload,
            status="initiated",
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        # Cache idempotency key (2h TTL — enough for redirect window)
        await redis.set(idem_key, str(txn.id), ttl=7200)

        DOWN_PAYMENT_TOTAL.labels(gateway="safepay", status="initiated").inc()
        return DownPaymentResponse(
            status="pending",
            order_id=order.id,
            payment_transaction_id=txn.id,
            payment_session_url=checkout.checkout_url,
            gateway_txn_id=checkout.gateway_txn_id,
            idempotency_key=request_payload.idempotency_key,
        )

    # ── JazzCash: direct synchronous charge ───────────────────────────────────
    if method == "jazzcash":
        try:
            jc = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD, settings.JAZZCASH_BASE_URL)
            result = jc.charge(order_id=order.id, amount_pkr=request_payload.amount_pkr)
        except Exception as exc:
            await routing.record_failure("jazzcash")
            GATEWAY_FAILURE_TOTAL.labels(gateway="jazzcash").inc()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GATEWAY_ERROR") from exc

        txn = PaymentTransaction(
            user_id=current_user.id,
            amount=request_payload.amount_pkr,
            currency=settings.PAYMENT_CURRENCY,
            gateway="jazzcash",
            gateway_txn_id=result.gateway_txn_id,
            gateway_response=result.payload,
            status="success",
            reconciled_at=datetime.now(timezone.utc),
        )
        db.add(txn)
        await db.flush()

        await service.confirm_down_payment(
            order_id=order.id,
            amount_pkr=request_payload.amount_pkr,
            gateway_txn_id=result.gateway_txn_id,
        )
        await service.queue_issue(
            order_id=order.id,
            amount_pkr=Decimal(str(order.total_amount)),
            merchant_domain=None,
        )
        await db.commit()
        await db.refresh(txn)

        await redis.set(idem_key, str(txn.id), ttl=7200)
        await routing.record_success("jazzcash")
        DOWN_PAYMENT_TOTAL.labels(gateway="jazzcash", status="success").inc()

        return DownPaymentResponse(
            status="success",
            order_id=order.id,
            payment_transaction_id=txn.id,
            gateway_txn_id=result.gateway_txn_id,
            idempotency_key=request_payload.idempotency_key,
        )

    # ── Raast: IBFT initiation ─────────────────────────────────────────────────
    if method == "raast":
        # Raast requires the payer's bank IBAN. We fetch the default Raast
        # payment method for the user.
        pm = await db.scalar(
            select(PaymentMethod).where(
                PaymentMethod.user_id == current_user.id,
                PaymentMethod.provider == "raast",
                PaymentMethod.is_default == True,
                PaymentMethod.deleted_at.is_(None),
            )
        )
        if not pm:
            logger.warning("No default Raast IBAN found for user", extra={"user_id": current_user.id})
            # Fallback to profile placeholder if no PM linked yet (for testing)
            payer_iban = "PK36SCBL0000001123456702"
        else:
            payer_iban = pm.tokenized_reference

        try:
            raast = RaastClient(
                api_key=settings.RAAST_API_KEY,
                api_secret=settings.RAAST_API_SECRET,
                merchant_iban=settings.RAAST_MERCHANT_IBAN,
                base_url=settings.RAAST_BASE_URL,
            )
            result = raast.initiate_ibft(
                order_id=order.id,
                amount_pkr=request_payload.amount_pkr,
                payer_iban=payer_iban,
                callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/raast",
            )
        except Exception as exc:
            await routing.record_failure("raast")
            GATEWAY_FAILURE_TOTAL.labels(gateway="raast").inc()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GATEWAY_ERROR") from exc

        txn = PaymentTransaction(
            user_id=current_user.id,
            amount=request_payload.amount_pkr,
            currency=settings.PAYMENT_CURRENCY,
            gateway="raast",
            gateway_txn_id=result.gateway_txn_id,
            gateway_response=result.payload,
            status="initiated",
        )
        db.add(txn)
        await db.commit()
        await db.refresh(txn)

        await redis.set(idem_key, str(txn.id), ttl=7200)
        DOWN_PAYMENT_TOTAL.labels(gateway="raast", status="initiated").inc()

        return DownPaymentResponse(
            status="pending",
            order_id=order.id,
            payment_transaction_id=txn.id,
            gateway_txn_id=result.gateway_txn_id,
            idempotency_key=request_payload.idempotency_key,
        )

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="UNSUPPORTED_METHOD")


@router.post("/pay-installment", response_model=PayInstallmentResponse)
async def pay_installment(
    request_payload: PayInstallmentRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Pay a specific installment (user-initiated).
    """
    from sk_shared.events import build_event_envelope, event_channel

    installment = await db.scalar(
        select(Installment).where(
            Installment.id == request_payload.installment_id,
            Installment.user_id == current_user.id,
            Installment.deleted_at.is_(None),
        )
    )
    if installment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSTALLMENT_NOT_FOUND")

    if installment.status == "paid":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="INSTALLMENT_ALREADY_PAID",
        )

    # Check for existing successful transaction as Orchestrator no longer mutates installment.status
    existing_txn = await db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.installment_id == installment.id,
            PaymentTransaction.status == "success",
            PaymentTransaction.deleted_at.is_(None),
        )
    )
    if existing_txn:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="INSTALLMENT_ALREADY_PAID",
        )

    method = request_payload.method.value
    gateway_txn_id = None

    try:
        if method == "jazzcash":
            jc = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)
            result = jc.charge(order_id=installment.loan_id, amount_pkr=Decimal(str(installment.total_amount)))
            gateway_txn_id = result.gateway_txn_id
        elif method == "raast":
            raast = RaastClient(
                api_key=settings.RAAST_API_KEY,
                api_secret=settings.RAAST_API_SECRET,
                merchant_iban=settings.RAAST_MERCHANT_IBAN,
            )
            raast_result = raast.initiate_ibft(
                order_id=installment.loan_id,
                amount_pkr=Decimal(str(installment.total_amount)),
                payer_iban="",  # TODO: From user payment methods
                callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/raast",
            )
            gateway_txn_id = raast_result.gateway_txn_id
        elif method == "safepay":
            safepay = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET)
            checkout = safepay.create_checkout(
                order_id=installment.loan_id,
                amount_pkr=Decimal(str(installment.total_amount)),
                callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/safepay",
            )
            gateway_txn_id = checkout.gateway_txn_id
    except Exception as exc:
        GATEWAY_FAILURE_TOTAL.labels(gateway=method).inc()
        logger.error("Installment payment failed", extra={"installment_id": installment.id, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GATEWAY_ERROR") from exc

    now = datetime.now(timezone.utc)
    txn = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=current_user.id,
        amount=Decimal(str(installment.total_amount)),
        currency=settings.PAYMENT_CURRENCY,
        gateway=method,
        gateway_txn_id=gateway_txn_id,
        status="success",
        reconciled_at=now,
    )
    # VIOLATION-04: Do NOT mutate installment status directly.
    # installment.status = "paid"
    # installment.paid_amount = installment.total_amount
    # installment.paid_at = now
    db.add(txn)
    await db.commit()
    await db.refresh(txn)

    # Publish installment paid event for Ledger
    EVENT_PAYMENT_INSTALLMENT_PAID = "payment.installment_paid"
    envelope = build_event_envelope(
        event=EVENT_PAYMENT_INSTALLMENT_PAID,
        source_service="payment-orchestrator",
        payload={
            "installment_id": installment.id,
            "loan_id": installment.loan_id,
            "user_id": current_user.id,
            "amount_pkr": str(installment.total_amount),
            "gateway_txn_id": gateway_txn_id,
        },
    )
    await redis.publish(event_channel(EVENT_PAYMENT_INSTALLMENT_PAID), envelope.to_json())

    INSTALLMENT_PAYMENT_TOTAL.labels(gateway=method, status="success").inc()

    # Find next pending installment for response
    next_inst = await db.scalar(
        select(Installment).where(
            Installment.loan_id == installment.loan_id,
            Installment.status == "pending",
            Installment.installment_number > installment.installment_number,
        ).order_by(Installment.installment_number.asc()).limit(1)
    )

    return PayInstallmentResponse(
        success=True,
        txn_id=txn.id,
        paid_at=now.isoformat(),
        next_installment_id=next_inst.id if next_inst else None,
    )


@router.post("/refund", response_model=RefundResponse)
async def initiate_refund(
    request_payload: RefundRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Initiate a refund for an order.

    Validates the order belongs to the requesting user.
    Publishes payment.refund_initiated event for Ledger Service.
    """
    # Verify the order belongs to this user
    order = await _get_order_for_user(db, request_payload.order_id, current_user.id)

    refund_service = RefundService(db, redis)
    refund_txn = await refund_service.initiate_refund(
        order_id=order.id,
        amount_pkr=request_payload.amount_pkr,
        reason=request_payload.reason,
        refund_reference=request_payload.refund_reference,
        requested_by_user_id=current_user.id,
    )

    return RefundResponse(
        refund_id=refund_txn.id,
        order_id=order.id,
        amount_pkr=request_payload.amount_pkr,
        status=refund_txn.status,
        gateway_refund_id=refund_txn.gateway_txn_id,
        reason=request_payload.reason,
    )


@router.post("/internal/trigger-installment", include_in_schema=False)
async def internal_trigger_installment(
    request: Request,
    payload: PayInstallmentRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_internal_token),
):
    """
    Internal endpoint for billing sweep to trigger installment collection.
    Secured by X-Internal-Token (constant-time HMAC comparison).
    """
    from sk_shared.events import build_event_envelope, event_channel

    installment = await db.scalar(
        select(Installment).where(
            Installment.id == payload.installment_id,
            Installment.deleted_at.is_(None),
        )
    )
    if installment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSTALLMENT_NOT_FOUND")

    if installment.status == "paid":
        return {"status": "already_paid", "installment_id": installment.id}

    # Billing sweep uses JazzCash direct charge (mandate-style)
    # TODO: Use Raast for auto-collection when mandate API is available
    routing = GatewayRoutingEngine(redis)
    try:
        jc = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)
        result = jc.charge(
            order_id=installment.loan_id,
            amount_pkr=Decimal(str(installment.total_amount)),
        )
    except Exception as exc:
        await routing.record_failure("jazzcash")
        installment.retry_count = (installment.retry_count or 0) + 1
        
        # INCOMPLETE-03: Installment Retry Escalation
        if installment.retry_count >= settings.MAX_INSTALLMENT_RETRIES:
            installment.status = "failed"
            logger.error(
                "Installment failed after max retries", 
                extra={"installment_id": installment.id, "retries": installment.retry_count}
            )
            # Emit installment failed event for Notification Service
            from sk_shared.events import build_event_envelope, event_channel
            EVENT_PAYMENT_INSTALLMENT_FAILED = "payment.installment_failed"
            envelope = build_event_envelope(
                event=EVENT_PAYMENT_INSTALLMENT_FAILED,
                source_service="payment-orchestrator",
                payload={
                    "installment_id": installment.id,
                    "loan_id": installment.loan_id,
                    "user_id": installment.user_id,
                    "retry_count": installment.retry_count,
                },
            )
            await redis.publish(event_channel(EVENT_PAYMENT_INSTALLMENT_FAILED), envelope.to_json())
        
        await db.commit()
        logger.error("Billing sweep charge failed", extra={"installment_id": installment.id, "error": str(exc)})
        GATEWAY_FAILURE_TOTAL.labels(gateway="jazzcash").inc()
        return {"status": "failed", "error": "GATEWAY_DECLINED", "installment_id": installment.id}

    if not result.success:
        await routing.record_failure("jazzcash")
        installment.retry_count = (installment.retry_count or 0) + 1
        
        if installment.retry_count >= settings.MAX_INSTALLMENT_RETRIES:
            installment.status = "failed"
            # Emit failure event (same as above, abstracted in production)
            from sk_shared.events import build_event_envelope, event_channel
            EVENT_PAYMENT_INSTALLMENT_FAILED = "payment.installment_failed"
            envelope = build_event_envelope(
                event=EVENT_PAYMENT_INSTALLMENT_FAILED,
                source_service="payment-orchestrator",
                payload={"installment_id": installment.id, "loan_id": installment.loan_id}
            )
            await redis.publish(event_channel(EVENT_PAYMENT_INSTALLMENT_FAILED), envelope.to_json())

        await db.commit()
        return {"status": "failed", "error": "JAZZCASH_DECLINED", "installment_id": installment.id}
    
    await routing.record_success("jazzcash")

    now = datetime.now(timezone.utc)
    txn = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=installment.user_id,
        amount=Decimal(str(installment.total_amount)),
        currency=settings.PAYMENT_CURRENCY,
        gateway="jazzcash",
        gateway_txn_id=result.gateway_txn_id,
        gateway_response=result.payload,
        status="success",
        reconciled_at=now,
    )
    # installment.status = "paid"
    # installment.paid_amount = installment.total_amount
    # installment.paid_at = now
    db.add(txn)
    await db.commit()
    await db.refresh(txn)

    # Notify Ledger
    EVENT_PAYMENT_INSTALLMENT_PAID = "payment.installment_paid"
    envelope = build_event_envelope(
        event=EVENT_PAYMENT_INSTALLMENT_PAID,
        source_service="payment-orchestrator",
        payload={
            "installment_id": installment.id,
            "loan_id": installment.loan_id,
            "user_id": installment.user_id,
            "amount_pkr": str(installment.total_amount),
            "gateway_txn_id": result.gateway_txn_id,
        },
    )
    await redis.publish(event_channel(EVENT_PAYMENT_INSTALLMENT_PAID), envelope.to_json())
    INSTALLMENT_PAYMENT_TOTAL.labels(gateway="jazzcash", status="success").inc()

    return {"status": "success", "txn_id": txn.id, "installment_id": installment.id}