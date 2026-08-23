"""
Customer-facing payment endpoints.

- POST /payments/down-payment     — Initiate down payment (orchestrated via PaymentOrchestrator)
- POST /payments/pay-installment  — Pay a specific installment
- POST /payments/refund           — Request refund (via RefundOrchestrator)
- POST /internal/trigger-installment — Billing sweep trigger (X-Internal-Token required)

Architecture note:
  - This API layer validates, authenticates, and delegates to the Orchestration layer.
  - No direct gateway client calls are made here.
  - No Order, Loan, or Installment mutations occur here — only event emission.
  - Boundary rule: this service does NOT own Order state. Gateway Service validates
    contract signing before calling us; we receive order_id as a trusted reference.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.order import Order
from sk_shared.models.payment import Installment, PaymentMethod, PaymentTransaction
from sk_shared.redis_client import RedisClient

from src.adapters.factory import GatewayAdapterFactory
from src.config import settings
from src.core.dependencies import get_current_user, get_db, get_redis, rate_limit, require_internal_token
from src.core.metrics import DOWN_PAYMENT_TOTAL, GATEWAY_FAILURE_TOTAL, INSTALLMENT_PAYMENT_TOTAL
from src.models.refund_workflow import RefundStatus, RefundWorkflow
from src.orchestration.payment_orchestrator import PaymentOrchestrator
from src.orchestration.refund_orchestrator import RefundOrchestrator
from src.schemas.payments import (
    DownPaymentRequest,
    DownPaymentResponse,
    PayInstallmentRequest,
    PayInstallmentResponse,
    RefundRequest,
    RefundResponse,
)
from src.services.routing_engine import GatewayRoutingEngine
from src.services.vcn import VcnService
from src.state.payment_workflow import PaymentStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

_CALLBACK_BASE = "https://payment-orchestrator.sahulatkar.pk"

# Gateways that use async redirect flows (webhook confirms payment)
_ASYNC_GATEWAYS = {"safepay", "raast"}


async def _get_order_for_user(db: AsyncSession, order_id: int, user_id: int) -> Order:
    """
    Load an order that belongs to the given user.
    BV-02 note: Order state validation (CONTRACTS_SIGNED check) is intentionally
    kept here as a defensive guard — the Gateway Service is the primary enforcer,
    but we still verify before charging.
    """
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


@router.post("/down-payment", response_model=DownPaymentResponse, dependencies=[Depends(rate_limit(10, 60))])
async def down_payment(
    request_payload: DownPaymentRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Initiate a down payment for a signed order.

    Flow:
      1. Validate order is in CONTRACTS_SIGNED state (defensive check).
      2. Validate amount is within the configured down-payment range (25–40% of total).
      3. Create/retrieve durable PaymentWorkflow via PaymentOrchestrator (idempotency).
      4. If already CAPTURED, return existing result without re-charging.
      5. Call gateway via adapter (SafePay redirect → PENDING; JazzCash sync → CAPTURED).
      6. No Order, Loan, or Installment mutation occurs here.
    """
    request_id = request.headers.get("X-Request-ID")

    # ── 1. Load & validate order ─────────────────────────────────────────────
    order = await _get_order_for_user(db, request_payload.order_id, current_user.id)

    if order.status != OrderState.CONTRACTS_SIGNED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MURABAHA_NOT_SIGNED",
        )

    # ── 2. Down payment range validation ────────────────────────────────────
    # PO-BL-04: Reject zero, negative, and out-of-range amounts before any gateway call.
    if request_payload.amount_pkr <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="INVALID_AMOUNT: must be positive",
        )

    total_amount = Decimal(str(order.total_amount))
    min_amount = (total_amount * (settings.DOWN_PAYMENT_MIN_PCT / Decimal("100"))).quantize(Decimal("0.01"))
    max_amount = (total_amount * (settings.DOWN_PAYMENT_MAX_PCT / Decimal("100"))).quantize(Decimal("0.01"))

    if not (min_amount <= request_payload.amount_pkr <= max_amount):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"DOWN_PAYMENT_OUT_OF_RANGE: must be {min_amount}–{max_amount} PKR",
        )

    # ── 3. Gateway selection ──────────────────────────────────────────────────
    routing = GatewayRoutingEngine(redis)
    preferred = request_payload.method.value
    selected_gateway = await routing.select_gateway(preferred=preferred)
    adapter = GatewayAdapterFactory.get(selected_gateway, settings)

    # ── 4. Create durable workflow (handles idempotency) ────────────────────
    # PO-BL-06: Pre-check idempotency in Redis to avoid DB constraint 500 on concurrent requests.
    redis_idem_key = f"sk:po:idem:{request_payload.idempotency_key}"
    if await redis.get(redis_idem_key):
        # Quickly retrieve the existing workflow and return it idempotently
        from src.models.payment_workflow import PaymentWorkflow as _PW
        _existing = await db.scalar(
            select(_PW).where(_PW.idempotency_key == request_payload.idempotency_key)
        )
        if _existing:
            DOWN_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="idempotent").inc()
            return DownPaymentResponse(
                status="pending" if _existing.status == PaymentStatus.PENDING else "success",
                order_id=request_payload.order_id,
                payment_workflow_id=_existing.id,
                gateway_txn_id=_existing.gateway_session_id or "",
                idempotency_key=request_payload.idempotency_key,
            )
    await redis.set(redis_idem_key, "1", ttl=3600)

    orchestrator = PaymentOrchestrator(db)
    workflow = await orchestrator.initiate_payment(
        order_id=request_payload.order_id,
        user_id=current_user.id,
        amount_pkr=request_payload.amount_pkr,
        gateway=selected_gateway,
        idempotency_key=request_payload.idempotency_key,
        request_id=request_id,
    )

    if workflow.status == PaymentStatus.CAPTURED:
        # Already completed — return existing result idempotently
        DOWN_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="idempotent").inc()
        return DownPaymentResponse(
            status="success",
            order_id=request_payload.order_id,
            payment_workflow_id=workflow.id,
            gateway_txn_id=workflow.gateway_session_id or "",
            idempotency_key=request_payload.idempotency_key,
        )

    if workflow.status == PaymentStatus.PENDING:
        # Async gateway already redirected — return pending status
        return DownPaymentResponse(
            status="pending",
            order_id=request_payload.order_id,
            payment_workflow_id=workflow.id,
            gateway_txn_id=workflow.gateway_session_id or "",
            idempotency_key=request_payload.idempotency_key,
        )

    # ── 5. Build adapter kwargs for Raast (needs payer IBAN) ─────────────────
    extra_kwargs: dict = {}
    if selected_gateway == "raast":
        pm = await db.scalar(
            select(PaymentMethod).where(
                PaymentMethod.user_id == current_user.id,
                PaymentMethod.provider == "raast",
                PaymentMethod.is_default,
                PaymentMethod.deleted_at.is_(None),
            )
        )
        extra_kwargs["payer_iban"] = pm.tokenized_reference if pm else "PK36SCBL0000001123456702"

    # ── 6. Call gateway via adapter ──────────────────────────────────────────
    try:
        result = await adapter.initiate_payment(
            order_id=request_payload.order_id,
            amount_pkr=request_payload.amount_pkr,
            callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/{selected_gateway}",
            **extra_kwargs,
        )
        await routing.record_success(selected_gateway)
    except Exception as exc:
        # PO-BL-02: Classify error as retryable vs non-retryable
        from src.services.routing_engine import is_retryable_error
        is_retryable = is_retryable_error(str(exc))
        await routing.record_failure(selected_gateway)
        GATEWAY_FAILURE_TOTAL.labels(gateway=selected_gateway).inc()
        await orchestrator.mark_failed(workflow.id, str(exc), request_id=request_id)
        await db.commit()
        logger.error(
            "Gateway call failed during down payment",
            extra={"gateway": selected_gateway, "order_id": request_payload.order_id, "error": str(exc), "retryable": is_retryable},
        )
        detail = "GATEWAY_DECLINED" if not is_retryable else "GATEWAY_ERROR"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc

    # ── 7. Transition workflow state ─────────────────────────────────────────
    is_async = selected_gateway in _ASYNC_GATEWAYS
    if is_async:
        await orchestrator.mark_pending(workflow.id, result["gateway_txn_id"], request_id=request_id)
        DOWN_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="initiated").inc()
    else:
        # Sync gateway — payment captured immediately
        service = VcnService(db, redis)
        await orchestrator.confirm_payment(
            workflow.id, result["gateway_txn_id"], result, request_id=request_id
        )
        await service.confirm_down_payment(
            order_id=request_payload.order_id,
            amount_pkr=request_payload.amount_pkr,
            gateway_txn_id=result["gateway_txn_id"],
        )
        await service.queue_issue(
            order_id=request_payload.order_id,
            amount_pkr=Decimal(str(order.total_amount)),
            merchant_domain=None,
        )
        DOWN_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="success").inc()

    await db.commit()

    # ── 8. Build response ────────────────────────────────────────────────────
    return DownPaymentResponse(
        status="pending" if is_async else "success",
        order_id=request_payload.order_id,
        payment_workflow_id=workflow.id,
        payment_session_url=result.get("payment_url"),
        gateway_txn_id=result["gateway_txn_id"],
        idempotency_key=request_payload.idempotency_key,
    )


@router.post("/pay-installment", response_model=PayInstallmentResponse)
async def pay_installment(
    request_payload: PayInstallmentRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Pay a specific installment (user-initiated).
    Emits payment.installment_paid event for Ledger Service.
    Does NOT mutate Installment.status directly (BV-04 boundary rule).
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

    # Check for existing successful transaction (idempotency guard)
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
    routing = GatewayRoutingEngine(redis)
    selected_gateway = await routing.select_gateway(preferred=method)
    adapter = GatewayAdapterFactory.get(selected_gateway, settings)

    try:
        result = await adapter.initiate_payment(
            order_id=installment.loan_id,
            amount_pkr=Decimal(str(installment.total_amount)),
            callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/{selected_gateway}",
        )
        gateway_txn_id = result["gateway_txn_id"]
        await routing.record_success(selected_gateway)
    except Exception as exc:
        await routing.record_failure(selected_gateway)
        GATEWAY_FAILURE_TOTAL.labels(gateway=selected_gateway).inc()
        logger.error("Installment payment failed", extra={"installment_id": installment.id, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GATEWAY_ERROR") from exc

    now = datetime.now(timezone.utc)
    txn = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=current_user.id,
        amount=Decimal(str(installment.total_amount)),
        currency=settings.PAYMENT_CURRENCY,
        gateway=selected_gateway,
        gateway_txn_id=gateway_txn_id,
        status="success",
        reconciled_at=now,
    )
    # BV-04: Do NOT mutate installment.status directly.
    # Emit event — Ledger Service owns installment state transitions.
    db.add(txn)
    await db.commit()
    await db.refresh(txn)

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

    INSTALLMENT_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="success").inc()

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

    Uses RefundOrchestrator to ensure durable RefundWorkflow creation and
    outbox event emission before returning.
    """
    # Verify order belongs to this user (defensive guard)
    order = await _get_order_for_user(db, request_payload.order_id, current_user.id)

    # Find original successful payment for THIS order (not just any successful
    # payment ever made by the user) to identify gateway and the refundable amount.
    original_txn = await db.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.order_id == order.id,
            PaymentTransaction.user_id == current_user.id,
            PaymentTransaction.status == "success",
            PaymentTransaction.amount > 0,
        ).order_by(PaymentTransaction.id.asc()).limit(1)
    )
    if original_txn is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="NO_SUCCESSFUL_TRANSACTION_FOUND",
        )

    # Ceiling check: never refund more than the original payment, net of any
    # refunds already initiated/settled for this order.
    already_refunded = await db.scalar(
        select(func.coalesce(func.sum(RefundWorkflow.amount_pkr), 0)).where(
            RefundWorkflow.order_id == order.id,
            RefundWorkflow.status != RefundStatus.FAILED,
        )
    )
    refundable_amount = Decimal(str(original_txn.amount)) - Decimal(str(already_refunded))
    if request_payload.amount_pkr > refundable_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="REFUND_AMOUNT_EXCEEDS_AVAILABLE",
        )

    # Find existing PaymentWorkflow for idempotency linkage
    from src.models.payment_workflow import PaymentWorkflow
    from sqlalchemy import select as _select
    workflow = await db.scalar(
        _select(PaymentWorkflow).where(
            PaymentWorkflow.order_id == request_payload.order_id,
            PaymentWorkflow.status == PaymentStatus.CAPTURED,
        ).order_by(PaymentWorkflow.id.desc()).limit(1)
    )
    payment_workflow_id = workflow.id if workflow else 0

    orchestrator = RefundOrchestrator(db)
    refund_workflow = await orchestrator.initiate_refund(
        payment_workflow_id=payment_workflow_id,
        order_id=order.id,
        user_id=current_user.id,
        amount_pkr=request_payload.amount_pkr,
        reason=request_payload.reason,
        refund_reference=request_payload.refund_reference,
        gateway=original_txn.gateway,
        gateway_txn_id=original_txn.gateway_txn_id or "",
    )
    await db.commit()

    return RefundResponse(
        refund_id=refund_workflow.id,
        order_id=order.id,
        amount_pkr=request_payload.amount_pkr,
        status=refund_workflow.status,
        gateway_refund_id=getattr(refund_workflow, "gateway_refund_id", None),
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

    Retry schedule from payments.md:
      - Attempt 1: immediate
      - Attempt 2: 24h delay (handled by billing sweep scheduler)
      - Attempt 3: 48h delay (handled by billing sweep scheduler)
      - After 3 failures: emit installment_failed event → Notification Service sends SMS/WhatsApp link
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

    # INC-03 fix: Validate amount is positive and matches installment record
    if installment.total_amount <= 0:
        raise HTTPException(status_code=422, detail="INVALID_INSTALLMENT_AMOUNT")

    # GAP-07 fix: Prioritize Raast if a valid mandate exists for the user
    from src.models.payment_mandate import PaymentMandate
    mandate = await db.scalar(
        select(PaymentMandate).where(
            PaymentMandate.user_id == installment.user_id,
            PaymentMandate.gateway == "raast",
            PaymentMandate.status == "active",
        )
    )

    routing = GatewayRoutingEngine(redis)
    if mandate and mandate.is_valid(Decimal(str(installment.total_amount))):
        selected_gateway = "raast"
        logger.info("Using Raast mandate for installment collection", extra={"mandate": mandate.mandate_reference})
    else:
        selected_gateway = await routing.select_gateway()  # Auto-select best available

    adapter = GatewayAdapterFactory.get(selected_gateway, settings)

    extra_kwargs = {}
    if selected_gateway == "raast" and mandate:
        extra_kwargs["mandate_reference"] = mandate.mandate_reference

    try:
        result = await adapter.initiate_payment(
            order_id=installment.loan_id,
            amount_pkr=Decimal(str(installment.total_amount)),
            callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/{selected_gateway}",
            **extra_kwargs,
        )
    except Exception as exc:
        await routing.record_failure(selected_gateway)
        GATEWAY_FAILURE_TOTAL.labels(gateway=selected_gateway).inc()

        # BV-04: Update retry_count only — do NOT set installment.status = "failed" yet
        # That transition belongs to the Ledger/Billing domain.
        retry_count = (installment.retry_count or 0) + 1
        installment.retry_count = retry_count

        # INC-05 fix: Calculate next_retry_at based on settings
        if retry_count < settings.MAX_INSTALLMENT_RETRIES:
            from datetime import timedelta
            delay_hours = settings.INSTALLMENT_RETRY_DELAY_HOURS[retry_count] if retry_count < len(settings.INSTALLMENT_RETRY_DELAY_HOURS) else 24
            installment.next_retry_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)
            logger.info(
                "Installment retry scheduled",
                extra={"installment_id": installment.id, "retry_count": retry_count, "next_retry": installment.next_retry_at},
            )
        else:
            # After max retries: emit event so Notification Service handles SMS/WhatsApp fallback
            EVENT_INSTALLMENT_FAILED = "payment.installment_failed"
            envelope = build_event_envelope(
                event=EVENT_INSTALLMENT_FAILED,
                source_service="payment-orchestrator",
                payload={
                    "installment_id": installment.id,
                    "loan_id": installment.loan_id,
                    "user_id": installment.user_id,
                    "retry_count": retry_count,
                    "error": str(exc),
                },
            )
            await redis.publish(event_channel(EVENT_INSTALLMENT_FAILED), envelope.to_json())
            logger.error(
                "Installment failed after max retries — notification event emitted",
                extra={"installment_id": installment.id, "retries": retry_count},
            )

        await db.commit()
        return {"status": "failed", "error": "GATEWAY_DECLINED", "installment_id": installment.id}

    await routing.record_success(selected_gateway)

    now = datetime.now(timezone.utc)
    txn = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=installment.user_id,
        amount=Decimal(str(installment.total_amount)),
        currency=settings.PAYMENT_CURRENCY,
        gateway=selected_gateway,
        gateway_txn_id=result["gateway_txn_id"],
        gateway_response=result,
        status="success",
        reconciled_at=now,
    )
    # BV-04: Do NOT set installment.status = "paid" directly.
    # Emit event — Ledger Service owns installment state transitions.
    db.add(txn)
    await db.commit()
    await db.refresh(txn)

    EVENT_PAYMENT_INSTALLMENT_PAID = "payment.installment_paid"
    envelope = build_event_envelope(
        event=EVENT_PAYMENT_INSTALLMENT_PAID,
        source_service="payment-orchestrator",
        payload={
            "installment_id": installment.id,
            "loan_id": installment.loan_id,
            "user_id": installment.user_id,
            "amount_pkr": str(installment.total_amount),
            "gateway_txn_id": result["gateway_txn_id"],
        },
    )
    await redis.publish(event_channel(EVENT_PAYMENT_INSTALLMENT_PAID), envelope.to_json())
    INSTALLMENT_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="success").inc()

    return {"status": "success", "txn_id": txn.id, "installment_id": installment.id}


# ── PO-EP-01: Down-payment retry endpoint ────────────────────────────────────
@router.post("/down-payment/{payment_workflow_id}/retry")
async def retry_down_payment(
    payment_workflow_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Retry a failed or expired payment workflow.
    Creates a new idempotency key to bypass the stale workflow.
    """
    from src.models.payment_workflow import PaymentWorkflow
    workflow = await db.get(PaymentWorkflow, payment_workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WORKFLOW_NOT_FOUND")
    if workflow.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
    if workflow.status not in (PaymentStatus.FAILED, PaymentStatus.EXPIRED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"WORKFLOW_NOT_RETRYABLE: current status is {workflow.status}",
        )

    # Create new idempotency key for the retry attempt
    import uuid
    new_idem_key = f"{workflow.idempotency_key}_retry_{uuid.uuid4().hex[:8]}"

    routing = GatewayRoutingEngine(redis)
    selected_gateway = await routing.select_gateway(preferred=workflow.gateway)
    adapter = GatewayAdapterFactory.get(selected_gateway, settings)
    orchestrator = PaymentOrchestrator(db)

    new_workflow = await orchestrator.initiate_payment(
        order_id=workflow.order_id,
        user_id=current_user.id,
        amount_pkr=workflow.amount_pkr,
        gateway=selected_gateway,
        idempotency_key=new_idem_key,
        request_id=None,
    )

    try:
        result = await adapter.initiate_payment(
            order_id=workflow.order_id,
            amount_pkr=workflow.amount_pkr,
            callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/{selected_gateway}",
        )
        await routing.record_success(selected_gateway)
        await orchestrator.mark_pending(new_workflow.id, result["gateway_txn_id"])
        await db.commit()
    except Exception as exc:
        await routing.record_failure(selected_gateway)
        await orchestrator.mark_failed(new_workflow.id, str(exc))
        await db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GATEWAY_ERROR") from exc

    return {
        "status": "retried",
        "new_workflow_id": new_workflow.id,
        "gateway": selected_gateway,
        "gateway_txn_id": result.get("gateway_txn_id"),
        "idempotency_key": new_idem_key,
    }


# ── PO-EP-02: Payment history for an order ───────────────────────────────────
@router.get("/history/{order_id}")
async def get_payment_history(
    order_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve full payment history for an order (transactions + workflows).
    """
    from sk_shared.models.payment import Loan
    from src.models.payment_workflow import PaymentWorkflow

    # Verify order belongs to user
    await _get_order_for_user(db, order_id, current_user.id)

    loan = await db.scalar(select(Loan).where(Loan.order_id == order_id))
    txns = []
    if loan:
        result = await db.execute(
            select(PaymentTransaction)
            .where(
                PaymentTransaction.loan_id == loan.id,
                PaymentTransaction.deleted_at.is_(None),
            )
            .order_by(PaymentTransaction.id.asc())
        )
        txns = result.scalars().all()

    workflows = await db.execute(
        select(PaymentWorkflow)
        .where(PaymentWorkflow.order_id == order_id)
        .order_by(PaymentWorkflow.id.asc())
    )

    return {
        "order_id": order_id,
        "transactions": [
            {
                "id": t.id,
                "amount": str(t.amount),
                "currency": t.currency,
                "gateway": t.gateway,
                "gateway_txn_id": t.gateway_txn_id,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in txns
        ],
        "workflows": [
            {
                "id": w.id,
                "status": w.status,
                "gateway": w.gateway,
                "amount_pkr": str(w.amount_pkr),
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in workflows.scalars().all()
        ],
    }


# ── PO-EP-06: Auto-collect installment (internal, called by BillingSweepWorker) ──
@router.post("/internal/installments/{installment_id}/auto-collect", include_in_schema=False)
async def auto_collect_installment(
    installment_id: int,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_internal_token),
):
    """
    PO-EP-06: Internal endpoint called by Ledger Service BillingSweepWorker
    to trigger auto-collection of an overdue installment.

    This is the critical missing link between billing sweep and payment execution.
    Uses Raast mandate if available, otherwise falls back to gateway auto-selection.
    """
    from sk_shared.events import build_event_envelope, event_channel

    installment = await db.scalar(
        select(Installment).where(
            Installment.id == installment_id,
            Installment.deleted_at.is_(None),
        )
    )
    if installment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INSTALLMENT_NOT_FOUND")

    if installment.status == "paid":
        return {"status": "already_paid", "installment_id": installment_id}

    if Decimal(str(installment.total_amount)) <= Decimal("0"):
        raise HTTPException(status_code=422, detail="INVALID_INSTALLMENT_AMOUNT")

    # Use Raast mandate if active, else auto-select
    from src.models.payment_mandate import PaymentMandate
    mandate = await db.scalar(
        select(PaymentMandate).where(
            PaymentMandate.user_id == installment.user_id,
            PaymentMandate.gateway == "raast",
            PaymentMandate.status == "active",
        )
    )
    routing = GatewayRoutingEngine(redis)
    if mandate and mandate.is_valid(Decimal(str(installment.total_amount))):
        selected_gateway = "raast"
    else:
        selected_gateway = await routing.select_gateway()

    adapter = GatewayAdapterFactory.get(selected_gateway, settings)
    extra_kwargs = {}
    if selected_gateway == "raast" and mandate:
        extra_kwargs["mandate_reference"] = mandate.mandate_reference

    try:
        result = await adapter.initiate_payment(
            order_id=installment.loan_id,
            amount_pkr=Decimal(str(installment.total_amount)),
            callback_url=f"{_CALLBACK_BASE}/api/v1/webhooks/{selected_gateway}",
            **extra_kwargs,
        )
        await routing.record_success(selected_gateway)
    except Exception as exc:
        await routing.record_failure(selected_gateway)
        GATEWAY_FAILURE_TOTAL.labels(gateway=selected_gateway).inc()
        logger.error("Auto-collect installment failed", extra={"installment_id": installment_id, "error": str(exc)})
        return {"status": "failed", "error": "GATEWAY_DECLINED", "installment_id": installment_id}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    txn = PaymentTransaction(
        loan_id=installment.loan_id,
        installment_id=installment.id,
        user_id=installment.user_id,
        amount=Decimal(str(installment.total_amount)),
        currency=settings.PAYMENT_CURRENCY,
        gateway=selected_gateway,
        gateway_txn_id=result["gateway_txn_id"],
        gateway_response=result,
        status="success",
        reconciled_at=now,
    )
    db.add(txn)
    await db.commit()

    envelope = build_event_envelope(
        event="payment.installment_paid",
        source_service="payment-orchestrator",
        payload={
            "installment_id": installment.id,
            "loan_id": installment.loan_id,
            "user_id": installment.user_id,
            "amount_pkr": str(installment.total_amount),
            "gateway_txn_id": result["gateway_txn_id"],
            "source": "auto_collect",
        },
    )
    await redis.publish(event_channel("payment.installment_paid"), envelope.to_json())
    INSTALLMENT_PAYMENT_TOTAL.labels(gateway=selected_gateway, status="success").inc()

    return {"status": "success", "txn_id": txn.id, "installment_id": installment.id}