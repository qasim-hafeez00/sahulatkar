"""
Gateway webhook ingestion.

Gateways call these endpoints after payment completion.
All webhooks are HMAC-verified, deduplicated, and idempotent.

Supported:
  - POST /webhooks/safepay      — SafePay payment confirmation
  - POST /webhooks/jazzcash     — JazzCash payment confirmation
  - POST /webhooks/raast        — Raast IBFT confirmation
"""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisTTL
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.dependencies import get_db, get_redis
from src.core.metrics import WEBHOOK_RECEIVED_TOTAL
from src.models.refund_workflow import RefundWorkflow
from src.orchestration.refund_orchestrator import RefundOrchestrator
from src.schemas.payments import WebhookAck
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.safepay import SafepayClient
import stripe
from src.services.vcn import VcnService
from src.orchestration.vcn_orchestrator import VcnOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


async def _dedupe_webhook(redis: RedisClient, body: bytes, signature: str) -> bool:
    """
    Prevent duplicate processing of retried webhook deliveries.
    Key is SHA-256 of (body + signature). TTL = 24h.
    Returns True if the webhook should be processed, False if duplicate.
    """
    dedup_key = f"sk:webhook:dedup:{hashlib.sha256(body + signature.encode('utf-8')).hexdigest()}"
    if await redis.get(dedup_key):
        return False
    await redis.set(dedup_key, "1", ttl=RedisTTL.WEBHOOK_DEDUP)
    return True


@router.post("/webhooks/safepay", response_model=WebhookAck)
async def safepay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    body = await request.body()
    signature = request.headers.get("X-Safepay-Signature", "")
    client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET)

    if not client.verify_signature(body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="safepay", outcome="invalid_sig").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    if not await _dedupe_webhook(redis, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="safepay", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    event = client.parse_event(body)
    event_status = event.get("status", "")

    if event_status not in {"PAID", "paid", "success"}:
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="safepay", outcome="ignored").inc()
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    await service.queue_issue(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        merchant_domain=event.get("merchant_domain"),
    )
    await db.commit()

    WEBHOOK_RECEIVED_TOTAL.labels(gateway="safepay", outcome="processed").inc()
    logger.info("SafePay webhook processed", extra={"order_id": event["order_id"]})
    return WebhookAck(status="ok")


@router.post("/webhooks/jazzcash", response_model=WebhookAck)
async def jazzcash_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    body = await request.body()
    signature = request.headers.get("X-JazzCash-Signature", "")
    client = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)

    if not client.verify_signature(body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="jazzcash", outcome="invalid_sig").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    if not await _dedupe_webhook(redis, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="jazzcash", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    event = client.parse_event(body)
    if event.get("status") != "success":
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="jazzcash", outcome="ignored").inc()
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    await service.queue_issue(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        merchant_domain=None,
    )
    await db.commit()

    WEBHOOK_RECEIVED_TOTAL.labels(gateway="jazzcash", outcome="processed").inc()
    logger.info("JazzCash webhook processed", extra={"order_id": event["order_id"]})
    return WebhookAck(status="ok")


@router.post("/webhooks/raast", response_model=WebhookAck)
async def raast_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Raast IBFT confirmation webhook.
    Sent by the aggregator when the payer confirms the OTP and the transfer clears.
    """
    body = await request.body()
    signature = request.headers.get("X-Raast-Signature", "")
    client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )

    if not client.verify_signature(body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="invalid_sig").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    if not await _dedupe_webhook(redis, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    event = client.parse_webhook(body)
    if event.get("status") != "success":
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="ignored").inc()
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    await service.queue_issue(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        merchant_domain=None,
    )
    await db.commit()

    WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="processed").inc()
    logger.info("Raast webhook processed", extra={"order_id": event["order_id"]})
    return WebhookAck(status="ok")


@router.post("/webhooks/raast/mandate", response_model=WebhookAck)
async def raast_mandate_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Raast Mandate confirmation webhook.
    Sent by the aggregator when the payer authorizes the mandate.
    """
    body = await request.body()
    signature = request.headers.get("X-Raast-Signature", "")
    client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )

    if not client.verify_signature(body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast_mandate", outcome="invalid_sig").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    if not await _dedupe_webhook(redis, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast_mandate", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    import json
    data = json.loads(body.decode("utf-8"))
    mandate_ref = data.get("mandate_reference")
    mandate_status = "active" if data.get("status") == "success" else "failed"

    if not mandate_ref:
        return WebhookAck(status="ignored")

    from sqlalchemy import select
    from src.models.payment_mandate import PaymentMandate

    mandate = await db.scalar(
        select(PaymentMandate).where(PaymentMandate.mandate_reference == mandate_ref)
    )
    if mandate:
        mandate.status = mandate_status
        await db.commit()

    WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast_mandate", outcome="processed").inc()
    logger.info("Raast mandate webhook processed", extra={"mandate_ref": mandate_ref, "status": mandate_status})
    return WebhookAck(status="ok")


async def _process_refund_completion_webhook(
    *,
    db: AsyncSession,
    redis: RedisClient,
    gateway: str,
    body: bytes,
    signature: str,
    verify_signature: Callable[[bytes, str], bool],
) -> WebhookAck:
    """
    Common handler for async refund-completion callbacks.

    RefundOrchestrator.initiate_refund settles refunds synchronously when the
    gateway adapter confirms immediately, but real gateways (SafePay/JazzCash/
    Raast in production) can also confirm a refund asynchronously after it was
    left PENDING. This is the completion path that wires RefundOrchestrator
    .settle_refund up to that async confirmation.
    """
    metric_gateway = f"{gateway}_refund"

    if not verify_signature(body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway=metric_gateway, outcome="invalid_sig").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    if not await _dedupe_webhook(redis, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway=metric_gateway, outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    data = json.loads(body.decode("utf-8"))
    refund_reference = data.get("refund_reference")
    gateway_refund_id = data.get("gateway_refund_id", "")
    event_status = data.get("status")

    if not refund_reference or event_status not in {"success", "settled", "completed"}:
        WEBHOOK_RECEIVED_TOTAL.labels(gateway=metric_gateway, outcome="ignored").inc()
        return WebhookAck(status="ignored")

    refund = await db.scalar(
        select(RefundWorkflow).where(RefundWorkflow.refund_reference == refund_reference)
    )
    if refund is None:
        WEBHOOK_RECEIVED_TOTAL.labels(gateway=metric_gateway, outcome="ignored").inc()
        return WebhookAck(status="ignored")

    orchestrator = RefundOrchestrator(db)
    await orchestrator.settle_refund(refund.id, gateway_refund_id or refund.gateway_refund_id or "")
    await db.commit()

    WEBHOOK_RECEIVED_TOTAL.labels(gateway=metric_gateway, outcome="processed").inc()
    logger.info(f"{gateway} refund webhook processed", extra={"refund_reference": refund_reference})
    return WebhookAck(status="ok")


@router.post("/webhooks/safepay/refund", response_model=WebhookAck)
async def safepay_refund_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    body = await request.body()
    signature = request.headers.get("X-Safepay-Signature", "")
    client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET)
    return await _process_refund_completion_webhook(
        db=db, redis=redis, gateway="safepay", body=body, signature=signature,
        verify_signature=client.verify_signature,
    )


@router.post("/webhooks/jazzcash/refund", response_model=WebhookAck)
async def jazzcash_refund_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    body = await request.body()
    signature = request.headers.get("X-JazzCash-Signature", "")
    client = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)
    return await _process_refund_completion_webhook(
        db=db, redis=redis, gateway="jazzcash", body=body, signature=signature,
        verify_signature=client.verify_signature,
    )


@router.post("/webhooks/raast/refund", response_model=WebhookAck)
async def raast_refund_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    body = await request.body()
    signature = request.headers.get("X-Raast-Signature", "")
    client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )
    return await _process_refund_completion_webhook(
        db=db, redis=redis, gateway="raast", body=body, signature=signature,
        verify_signature=client.verify_signature,
    )


@router.post("/webhooks/stripe", response_model=WebhookAck)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """
    Stripe Issuing webhook handler.
    Tracks VCN authorizations and transactions.
    """
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    if not endpoint_secret:
        if settings.ENVIRONMENT != "local":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="STRIPE_WEBHOOK_NOT_CONFIGURED")
        logger.warning("STRIPE_WEBHOOK_SECRET not configured, skipping verification")
        # In dev, we might skip signature verification if secret is missing
        import json
        event = json.loads(payload)
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_PAYLOAD")
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    # Deduplication
    if sig_header and not await _dedupe_webhook(redis, payload, sig_header):
        return WebhookAck(status="duplicate")

    orchestrator = VcnOrchestrator(db)
    # Stripe events have type and data.object
    await orchestrator.handle_stripe_event(event["type"], event["data"]["object"])
    
    await db.commit()
    
    WEBHOOK_RECEIVED_TOTAL.labels(gateway="stripe", outcome="processed").inc()
    logger.info(f"Stripe webhook {event['type']} processed")
    return WebhookAck(status="ok")