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
    # M-02 FIX: Warn if secret is missing instead of silently skipping
    if not secret:
        logger.warning("WEBHOOK_SECRET_MISSING: Signature verification skipped because secret is not configured")
        return
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
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


async def _enqueue_webhook(redis: RedisClient, payload: dict) -> None:
    if hasattr(redis, "redis"):
        await redis.redis.lpush(QueueName.PAYMENT_WEBHOOK, json.dumps(payload)) # GAP-09


@router.post("/payment/jazzcash")
async def jazzcash_webhook(request: Request, redis: RedisClient = Depends(get_redis)) -> dict:
    _enforce_json_content_type(request)
    raw_body = await request.body()
    _verify_signature(settings.JAZZCASH_WEBHOOK_SECRET, raw_body, request.headers.get("X-JazzCash-Signature", ""))
    payload = await request.json()
    status_value = "confirmed" if str(payload.get("pp_ResponseCode")) == "000" else "failed"
    await _enqueue_webhook(
        redis,
        {
            "event": "webhook.payment_received",
            "gateway": "jazzcash",
            "status": status_value,
            "raw": payload,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"received": True, "gateway": "jazzcash"}


@router.post("/payment/safepay")
async def safepay_webhook(request: Request, redis: RedisClient = Depends(get_redis)) -> dict:
    _enforce_json_content_type(request)
    raw_body = await request.body()
    _verify_signature(settings.SAFEPAY_WEBHOOK_SECRET, raw_body, request.headers.get("X-SafePay-Signature", ""))
    payload = await request.json()
    await _enqueue_webhook(
        redis,
        {
            "event": "webhook.payment_received",
            "gateway": "safepay",
            "raw": payload,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"received": True, "gateway": "safepay"}