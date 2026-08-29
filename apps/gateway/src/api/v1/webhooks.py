from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName
from sk_shared.models.webhook import ProcessedWebhookEvent
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.core.dependencies import get_db, get_redis
from src.core.logging import logger

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(secret: str | None, raw_body: bytes, signature: str) -> None:
    if not secret:
        logger.error("WEBHOOK_SECRET_MISSING: refusing webhook because secret is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WEBHOOK_SECRET_NOT_CONFIGURED",
        )
    expected = hmac.new(secret.encode(), raw_body, digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_WEBHOOK_SIGNATURE")


def _enforce_json_content_type(request: Request) -> None:
    # SEC-04 FIX: Validate Content-Type to prevent MIME-type confusion attacks
    ct = request.headers.get("Content-Type", "")
    if "application/json" not in ct.lower():
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 
            detail="UNSUPPORTED_CONTENT_TYPE: application/json required"
        )


def _enforce_payload_size(raw_body: bytes) -> None:
    if len(raw_body) > settings.WEBHOOK_MAX_BODY_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="WEBHOOK_PAYLOAD_TOO_LARGE",
        )


async def _enqueue_webhook(
    redis: RedisClient,
    payload: dict,
    idempotency_key: str | None = None,
    *,
    gateway: str = "unknown",
    db: AsyncSession | None = None,
) -> None:
    """MEDIUM fix: dedup used to be a 24h Redis SETNX marker only, with no
    fallback -- a retried webhook arriving after the Redis key expired/was
    evicted, or while Redis itself is unavailable, would be silently
    re-enqueued and reprocessed with nothing to catch it. `processed_webhook_events`
    is a second, durable layer: checked whenever Redis doesn't have the key
    (whether because it genuinely isn't there, or because Redis errored),
    and written to alongside the Redis marker so the next retry has both
    layers to check.
    """
    if idempotency_key:
        cache_key = f"sk:webhook:processed:{idempotency_key}"

        redis_hit = False
        if hasattr(redis, "redis"):
            try:
                redis_hit = bool(await redis.redis.get(cache_key))
            except Exception as exc:
                logger.warning("WEBHOOK_DEDUP_REDIS_UNAVAILABLE key=%s error=%s -- falling back to DB", idempotency_key, exc)

        if redis_hit:
            logger.info("Webhook duplicate skipped (redis): %s", idempotency_key)
            return

        if db is not None:
            existing = await db.scalar(
                select(ProcessedWebhookEvent).where(ProcessedWebhookEvent.idempotency_key == idempotency_key)
            )
            if existing is not None:
                logger.info("Webhook duplicate skipped (db fallback): %s", idempotency_key)
                # Redis marker was missing/expired but the DB row wasn't -- repair the
                # fast-path cache so the next retry doesn't need the DB round-trip.
                if hasattr(redis, "redis"):
                    try:
                        await redis.redis.set(cache_key, "1", ex=86400)
                    except Exception:
                        pass
                return

        if hasattr(redis, "redis"):
            try:
                await redis.redis.set(cache_key, "1", ex=86400)
            except Exception as exc:
                logger.warning("WEBHOOK_DEDUP_REDIS_SET_FAILED key=%s error=%s", idempotency_key, exc)

        if db is not None:
            db.add(ProcessedWebhookEvent(
                idempotency_key=idempotency_key,
                gateway=gateway,
                processed_at=datetime.now(timezone.utc),
            ))
            try:
                await db.commit()
            except IntegrityError:
                # Lost a race against a concurrent duplicate -- the other request's
                # row already recorded this key; nothing more to do.
                await db.rollback()

    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.PAYMENT_WEBHOOK, json.dumps(payload)) # GAP-09


@router.post("/payment/jazzcash")
async def jazzcash_webhook(
    request: Request,
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _enforce_json_content_type(request)
    raw_body = await request.body()
    _enforce_payload_size(raw_body)
    _verify_signature(settings.JAZZCASH_WEBHOOK_SECRET, raw_body, request.headers.get("X-JazzCash-Signature", ""))
    payload = await request.json()
    status_value = "confirmed" if str(payload.get("pp_ResponseCode")) == "000" else "failed"
    txn_ref = payload.get("pp_TxnRefNo")
    idempotency_key = f"jazzcash:{txn_ref}" if txn_ref else None

    await _enqueue_webhook(
        redis,
        {
            "event": "webhook.payment_received",
            "gateway": "jazzcash",
            "status": status_value,
            "raw": payload,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        },
        idempotency_key,
        gateway="jazzcash",
        db=db,
    )
    return {"received": True, "gateway": "jazzcash"}


@router.post("/payment/safepay")
async def safepay_webhook(
    request: Request,
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _enforce_json_content_type(request)
    raw_body = await request.body()
    _enforce_payload_size(raw_body)
    _verify_signature(settings.SAFEPAY_WEBHOOK_SECRET, raw_body, request.headers.get("X-SafePay-Signature", ""))
    payload = await request.json()
    tracker = payload.get("tracker")
    idempotency_key = f"safepay:{tracker}" if tracker else None

    await _enqueue_webhook(
        redis,
        {
            "event": "webhook.payment_received",
            "gateway": "safepay",
            "raw": payload,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        },
        idempotency_key,
        gateway="safepay",
        db=db,
    )
    return {"received": True, "gateway": "safepay"}


# ── MISS-03: Stripe Webhook (VCN Confirmation) ────────────────────────────────

def _verify_stripe_signature(secret: str, raw_body: bytes, stripe_sig_header: str) -> None:
    """Verify Stripe webhook signature using HMAC-SHA256 without importing the stripe library."""
    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET_MISSING: refusing webhook because secret is not configured")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="STRIPE_WEBHOOK_SECRET_NOT_CONFIGURED")
    # Stripe-Signature header format: t=<timestamp>,v1=<hash>[,v0=<hash>]
    parts = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in stripe_sig_header.split(",") if "=" in kv}
    timestamp = parts.get("t", "")
    v1 = parts.get("v1", "")
    if not timestamp or not v1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_STRIPE_SIGNATURE_FORMAT")
    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(secret.encode(), signed_payload, digestmod=hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_STRIPE_SIGNATURE")


_STRIPE_ROUTABLE_EVENTS = {
    "issuing_authorization.request",
    "issuing_transaction.created",
    "issuing_card.updated",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
}


@router.post("/payment/stripe")
async def stripe_webhook(
    request: Request,
    redis: RedisClient = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _enforce_json_content_type(request)
    raw_body = await request.body()
    _enforce_payload_size(raw_body)
    sig_header = request.headers.get("Stripe-Signature", "")
    _verify_stripe_signature(settings.STRIPE_WEBHOOK_SECRET, raw_body, sig_header)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_JSON")

    event_type = payload.get("type", "unknown")
    event_id = payload.get("id")
    idempotency_key = f"stripe:{event_id}" if event_id else None

    if event_type not in _STRIPE_ROUTABLE_EVENTS:
        logger.info("Stripe event type=%s not routed — acknowledged but ignored", event_type)
        return {"received": True, "gateway": "stripe", "routed": False}

    await _enqueue_webhook(
        redis,
        {
            "event": f"stripe.{event_type}",
            "gateway": "stripe",
            "raw": payload,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        },
        idempotency_key,
        gateway="stripe",
        db=db,
    )
    return {"received": True, "gateway": "stripe", "routed": True}