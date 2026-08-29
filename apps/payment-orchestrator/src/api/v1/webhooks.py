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


async def _dedupe_webhook(
    redis: RedisClient,
    gateway: str,
    stable_id: str | None,
    body: bytes,
    signature: str,
) -> bool:
    """
    Prevent duplicate processing of retried webhook deliveries.

    PO-CRIT-04: Keyed primarily on a stable identifier pulled out of the
    gateway's own payload (gateway_txn_id / refund_reference /
    mandate_reference / Stripe event id — whichever that gateway's event
    carries), not on SHA-256(body + signature). A legitimate retry of the
    *same* logical event from the gateway is not guaranteed to be
    byte-identical to the original delivery (re-signed timestamp, reordered
    fields, added metadata, etc.), so hashing the raw body silently fails to
    recognize it as a repeat and lets it double-process. Falls back to the
    body+signature hash only when this specific gateway's payload carries no
    such identifier (e.g. malformed/legacy payloads) — namespaced per
    gateway either way so two gateways' ids can never collide. TTL = 24h.

    Returns True if the webhook should be processed, False if duplicate.
    """
    if stable_id:
        dedup_key = f"sk:webhook:dedup:{gateway}:{stable_id}"
    else:
        body_hash = hashlib.sha256(body + signature.encode("utf-8")).hexdigest()
        dedup_key = f"sk:webhook:dedup:{gateway}:hash:{body_hash}"
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
    client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET)

    if not client.verify_signature(body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="safepay", outcome="invalid_sig").inc()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")

    # PO-CRIT-04: parse before dedup so we can key on the gateway's own
    # stable transaction id instead of a raw body+signature hash.
    event = client.parse_event(body)

    if not await _dedupe_webhook(redis, "safepay", event.get("gateway_txn_id") or None, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="safepay", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

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
    # Live-tested bug: this used to pass event["amount_pkr"] — the DOWN
    # PAYMENT amount just confirmed — as the VCN's authorized amount.
    # VcnService.issue_vcn() compares amount_pkr against the order's stored
    # total_amount (see PRICE_DRIFT_EXCEEDED), so a real SafePay/Raast down
    # payment always failed VCN issuance, retried with backoff, and never
    # succeeded — the VCN must cover the full merchant purchase price, not
    # just the down payment. Matches the sync-gateway path in gateway's own
    # payments.py / payment-orchestrator's payments.py down_payment endpoint,
    # both of which already correctly use order.total_amount here.
    order = await service._get_order(int(event["order_id"]))
    await service.queue_issue(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(order.total_amount)),
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

    event = client.parse_event(body)

    if not await _dedupe_webhook(redis, "jazzcash", event.get("gateway_txn_id") or None, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="jazzcash", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    if event.get("status") != "success":
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="jazzcash", outcome="ignored").inc()
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    # Same PRICE_DRIFT_EXCEEDED bug as the SafePay handler above — VCN amount
    # must be the order's full total, not the down payment just confirmed.
    order = await service._get_order(int(event["order_id"]))
    await service.queue_issue(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(order.total_amount)),
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

    event = client.parse_webhook(body)

    if not await _dedupe_webhook(redis, "raast", event.get("gateway_txn_id") or None, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

    if event.get("status") != "success":
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="ignored").inc()
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(event["amount_pkr"])),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    # Same PRICE_DRIFT_EXCEEDED bug as the SafePay handler above — VCN amount
    # must be the order's full total, not the down payment just confirmed.
    order = await service._get_order(int(event["order_id"]))
    await service.queue_issue(
        order_id=int(event["order_id"]),
        amount_pkr=Decimal(str(order.total_amount)),
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

    import json
    data = json.loads(body.decode("utf-8"))
    mandate_ref = data.get("mandate_reference")

    if not await _dedupe_webhook(redis, "raast_mandate", mandate_ref, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast_mandate", outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

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

    data = json.loads(body.decode("utf-8"))
    refund_reference = data.get("refund_reference")

    if not await _dedupe_webhook(redis, metric_gateway, refund_reference, body, signature):
        WEBHOOK_RECEIVED_TOTAL.labels(gateway=metric_gateway, outcome="duplicate").inc()
        return WebhookAck(status="duplicate")

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
    client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET)
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
        if not settings.test_payment_fallbacks_enabled:
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

    # Deduplication — keyed on Stripe's own event id (`evt_...`), which is
    # already the canonical idempotency key Stripe recommends for this
    # exact purpose, rather than a hash of the raw delivery.
    stripe_event_id = event.get("id") if hasattr(event, "get") else None
    if sig_header and not await _dedupe_webhook(redis, "stripe", stripe_event_id, payload, sig_header):
        return WebhookAck(status="duplicate")

    orchestrator = VcnOrchestrator(db, redis)
    # Stripe events have type and data.object
    await orchestrator.handle_stripe_event(event["type"], event["data"]["object"])
    
    await db.commit()
    
    WEBHOOK_RECEIVED_TOTAL.labels(gateway="stripe", outcome="processed").inc()
    logger.info(f"Stripe webhook {event['type']} processed")
    return WebhookAck(status="ok")