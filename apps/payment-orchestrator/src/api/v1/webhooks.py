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
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisTTL
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.dependencies import get_db, get_redis
from src.core.metrics import WEBHOOK_RECEIVED_TOTAL
from src.schemas.payments import WebhookAck
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.safepay import SafepayClient
from src.services.vcn import VcnService

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

    WEBHOOK_RECEIVED_TOTAL.labels(gateway="raast", outcome="processed").inc()
    logger.info("Raast webhook processed", extra={"order_id": event["order_id"]})
    return WebhookAck(status="ok")