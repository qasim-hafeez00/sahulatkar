from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.order import Order
from sk_shared.models.payment import Installment, PaymentTransaction
from sk_shared.redis_client import RedisClient

from src.core.dependencies import get_current_user, get_db, get_redis
from src.schemas.payments import DownPaymentRequest, DownPaymentResponse, PayInstallmentRequest, PayInstallmentResponse
from src.services.jazzcash import JazzCashClient
from src.services.safepay import SafepayClient
from src.services.vcn import VcnService
from src.config import settings

router = APIRouter(prefix="/payments", tags=["payments"])


async def _get_order_for_user(db: AsyncSession, order_id: int, user_id: int) -> Order:
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user_id, Order.deleted_at.is_(None)))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    return order


@router.post("/down-payment", response_model=DownPaymentResponse)
async def down_payment(
    request_payload: DownPaymentRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    from decimal import Decimal
    order = await _get_order_for_user(db, request_payload.order_id, current_user.id)
    if order.status != OrderState.CONTRACTS_SIGNED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MURABAHA_NOT_SIGNED")

    total_amount = Decimal(str(order.total_amount))
    min_pct = Decimal(str(settings.DOWN_PAYMENT_MIN_PCT))
    max_pct = Decimal(str(settings.DOWN_PAYMENT_MAX_PCT))
    
    min_amount = total_amount * (min_pct / Decimal("100.0"))
    max_amount = total_amount * (max_pct / Decimal("100.0"))
    
    if not (min_amount <= request_payload.amount_pkr <= max_amount):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="DOWN_PAYMENT_OUT_OF_RANGE")

    transaction = PaymentTransaction(
        user_id=current_user.id,
        amount=request_payload.amount_pkr,
        currency=settings.PAYMENT_CURRENCY,
        gateway=request_payload.method.value,
        status="initiated",
    )
    db.add(transaction)
    await db.flush()

    service = VcnService(db, redis)
    callback_url = "https://payment-orchestrator.local/webhooks/safepay"

    if request_payload.method.value == "safepay":
        safepay = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET)
        checkout = safepay.create_checkout(order_id=order.id, amount_pkr=request_payload.amount_pkr, callback_url=callback_url)
        transaction.gateway_txn_id = checkout.gateway_txn_id
        transaction.gateway_response = checkout.payload
        await db.commit()
        return DownPaymentResponse(
            status="pending",
            order_id=order.id,
            payment_transaction_id=transaction.id,
            payment_session_url=checkout.checkout_url,
            gateway_txn_id=checkout.gateway_txn_id,
        )

    jazzcash = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)
    result = jazzcash.charge(order_id=order.id, amount_pkr=request_payload.amount_pkr)
    transaction.gateway_txn_id = result.gateway_txn_id
    transaction.gateway_response = result.payload
    transaction.status = "success"
    transaction.reconciled_at = datetime.now(timezone.utc)
    await service.confirm_down_payment(order_id=order.id, amount_pkr=request_payload.amount_pkr, gateway_txn_id=result.gateway_txn_id)
    await service.queue_issue(order_id=order.id, amount_pkr=order.total_amount, merchant_domain=None)
    await db.commit()
    return DownPaymentResponse(
        status="success",
        order_id=order.id,
        payment_transaction_id=transaction.id,
        gateway_txn_id=result.gateway_txn_id,
    )


@router.post("/pay-installment", response_model=PayInstallmentResponse)
async def pay_installment(
    request_payload: PayInstallmentRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    installment = await db.scalar(
        select(Installment).where(Installment.id == request_payload.installment_id, Installment.user_id == current_user.id, Installment.deleted_at.is_(None))
    )
    if installment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSTALLMENT_NOT_FOUND")

    transaction = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=current_user.id,
        amount=float(installment.total_amount),
        currency=settings.PAYMENT_CURRENCY,
        gateway=request_payload.method.value,
        status="success",
        reconciled_at=datetime.now(timezone.utc),
    )
    installment.status = "paid"
    installment.paid_amount = installment.total_amount
    installment.paid_at = datetime.now(timezone.utc)
    db.add(transaction)
    await db.commit()

    return PayInstallmentResponse(
        success=True,
        txn_id=transaction.id,
        paid_at=installment.paid_at.isoformat(),
        next_installment_id=None,
    )


@router.post("/internal/trigger-installment", include_in_schema=False)
async def internal_trigger_installment(
    request: PayInstallmentRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    # This is an internal-only endpoint for the billing sweep
    # In a real app, this would be secured by inter-service auth (e.g. shared secret or MTLS)
    installment = await db.scalar(
        select(Installment).where(Installment.id == request.installment_id, Installment.deleted_at.is_(None))
    )
    if installment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSTALLMENT_NOT_FOUND")

    if installment.status == "paid":
        return {"status": "already_paid", "installment_id": installment.id}

    jazzcash = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)
    # Use the phone number from the installment/loan metadata if available, otherwise fallback
    result = jazzcash.charge(order_id=installment.loan_id, amount_pkr=float(installment.total_amount))
    
    if not result.success:
        installment.retry_count += 1
        await db.commit()
        return {"status": "failed", "error": "JAZZCASH_DECLINED"}

    transaction = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=installment.user_id,
        amount=float(installment.total_amount),
        currency=settings.PAYMENT_CURRENCY,
        gateway="jazzcash",
        gateway_txn_id=result.gateway_txn_id,
        status="success",
        reconciled_at=datetime.now(timezone.utc),
    )
    installment.status = "paid"
    installment.paid_amount = installment.total_amount
    installment.paid_at = datetime.now(timezone.utc)
    db.add(transaction)
    await db.commit()

    return {"status": "success", "txn_id": transaction.id}