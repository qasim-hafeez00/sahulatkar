import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS, RedisTTL
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.dependencies import get_aftership_client, get_db, get_redis
from src.schemas.tracking import WebhookAck
from src.services.aftership_client import AfterShipClient
from src.services.tracking_service import TrackingService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/aftership", response_model=WebhookAck)
async def aftership_webhook(
    request: Request,
    x_aftership_hmac_sha256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    aftership: AfterShipClient = Depends(get_aftership_client),
):
    raw = await request.body()
    signature = x_aftership_hmac_sha256 or ""
    if not AfterShipClient.verify_hmac(raw, signature, settings.AFTERSHIP_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_WEBHOOK_SIGNATURE")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="INVALID_WEBHOOK_PAYLOAD") from exc

    dedup = TrackingService.dedup_hash(payload)
    dedup_key = f"{RedisNS.WEBHOOK_DEDUP}:{dedup}"
    if await redis.get(dedup_key):
        return WebhookAck(received=True)

    service = TrackingService(db=db, redis=redis, aftership=aftership)
    await service.process_aftership_webhook(payload)
    await redis.set(dedup_key, "1", ttl=RedisTTL.WEBHOOK_DEDUP)
    return WebhookAck(received=True)
