from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisTTL
from sk_shared.redis_client import RedisClient

from src.core.dependencies import get_db, get_redis
from src.schemas.payments import WebhookAck
from src.services.jazzcash import JazzCashClient
from src.services.safepay import SafepayClient
from src.services.vcn import VcnService
from src.config import settings

router = APIRouter(tags=["webhooks"])


async def _dedupe_webhook(redis: RedisClient, body: bytes, signature: str) -> bool:
    dedup_key = hashlib.sha256(body + signature.encode("utf-8")).hexdigest()
    key = f"sk:webhook:dedup:{dedup_key}"
    if await redis.get(key):
        return False
    await redis.set(key, "1", ttl=RedisTTL.WEBHOOK_DEDUP)
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")
    if not await _dedupe_webhook(redis, body, signature):
        return WebhookAck(status="duplicate")

    event = client.parse_event(body)
    if event.get("status") not in {"PAID", "paid", "success"}:
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=float(event["amount_pkr"]),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    await service.queue_issue(order_id=int(event["order_id"]), amount_pkr=float(event["amount_pkr"]), merchant_domain=event.get("merchant_domain"))
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_SIGNATURE")
    if not await _dedupe_webhook(redis, body, signature):
        return WebhookAck(status="duplicate")

    event = client.parse_event(body)
    if event.get("pp_ResponseCode") != "000":
        return WebhookAck(status="ignored")

    service = VcnService(db, redis)
    await service.confirm_down_payment(
        order_id=int(event["order_id"]),
        amount_pkr=float(event["amount_pkr"]),
        gateway_txn_id=event.get("gateway_txn_id", ""),
    )
    await service.queue_issue(order_id=int(event["order_id"]), amount_pkr=float(event["amount_pkr"]), merchant_domain=event.get("merchant_domain"))
    return WebhookAck(status="ok")