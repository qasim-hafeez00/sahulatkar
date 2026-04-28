from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from sk_shared.constants import QueueName
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.core.dependencies import get_redis
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


async def _enqueue_webhook(redis: RedisClient, payload: dict, idempotency_key: str | None = None) -> None:
    if hasattr(redis, "redis"):
        if idempotency_key:
            cache_key = f"sk:webhook:processed:{idempotency_key}"
            if await redis.redis.get(cache_key):
                logger.info("Webhook duplicate skipped: %s", idempotency_key)
                return
            await redis.redis.set(cache_key, "1", ex=86400)
        await redis.redis.lpush(QueueName.PAYMENT_WEBHOOK, json.dumps(payload)) # GAP-09


@router.post("/payment/jazzcash")
async def jazzcash_webhook(request: Request, redis: RedisClient = Depends(get_redis)) -> dict:
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
    )
    return {"received": True, "gateway": "jazzcash"}


@router.post("/payment/safepay")
async def safepay_webhook(request: Request, redis: RedisClient = Depends(get_redis)) -> dict:
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
    )
    return {"received": True, "gateway": "safepay"}