import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.notification import NotificationDispatch, DispatchStatus

from sk_shared.constants import RedisNS, RedisTTL
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.dependencies import get_aftership_client, get_db, get_redis
from src.core.utils import verify_hmac
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

@router.post("/sendgrid")
async def sendgrid_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Process SendGrid Event Webhooks for delivery and unsubscribe tracking.
    """
    payload = await request.json()
    # Payload is a list of events
    for event in payload:
        event_type = event.get("event")
        message_id = event.get("sg_message_id")
        
        if not message_id:
            continue
            
        # Strip provider-specific suffix if needed
        clean_id = message_id.split(".")[0]
        
        # Find dispatch
        stmt = select(NotificationDispatch).where(NotificationDispatch.provider_message_id == clean_id)
        dispatch = await db.scalar(stmt)
        
        if not dispatch:
            continue
            
        if event_type in ("delivered", "open", "click"):
            dispatch.status = DispatchStatus.DELIVERED
            dispatch.delivered_at = datetime.now(timezone.utc)
        elif event_type in ("bounce", "dropped", "deferred"):
            dispatch.status = DispatchStatus.FAILED
            dispatch.failure_reason = event.get("reason", event_type)
            dispatch.failed_at = datetime.now(timezone.utc)
        elif event_type in ("spamreport", "unsubscribe"):
            # Disable email for the specific category that triggered this notification
            from sk_shared.models.notification import NotificationPreference, Notification
            from sqlalchemy import update
            
            # Find the original notification to get its category
            notification = await db.get(Notification, dispatch.notification_id)
            if notification:
                stmt = update(NotificationPreference).where(
                    NotificationPreference.user_id == notification.user_id,
                    NotificationPreference.category == notification.category
                ).values(email_enabled=False)
                await db.execute(stmt)
            
    await db.commit()
    return {"status": "ok"}

@router.post("/sms-delivery")
async def sms_delivery_receipt(
    request: Request,
    x_jazz_hmac_sha256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Generic endpoint for SMS delivery reports (Jazz/Twilio).
    """
    raw = await request.body()
    if settings.JAZZ_SMS_WEBHOOK_SECRET:
        if not verify_hmac(raw, x_jazz_hmac_sha256 or "", settings.JAZZ_SMS_WEBHOOK_SECRET):
            raise HTTPException(status_code=403, detail="INVALID_SIGNATURE")

    payload = json.loads(raw.decode("utf-8"))
    message_id = payload.get("message_id") or payload.get("MessageSid")
    status = payload.get("status") or payload.get("SmsStatus")
    
    if not message_id:
        return {"status": "ignored"}
        
    stmt = select(NotificationDispatch).where(NotificationDispatch.provider_message_id == message_id)
    dispatch = await db.scalar(stmt)
    
    if dispatch:
        if status in ("delivered", "sent", "success"):
            dispatch.status = DispatchStatus.DELIVERED
            dispatch.delivered_at = datetime.now(timezone.utc)
        elif status in ("failed", "undelivered", "rejected"):
            dispatch.status = DispatchStatus.FAILED
            dispatch.failed_at = datetime.now(timezone.utc)
            dispatch.failure_reason = status
            
        await db.commit()
        
    return {"status": "accepted"}

@router.post("/whatsapp-delivery")
async def whatsapp_delivery_receipt(
    request: Request,
    x_whatsapp_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Generic endpoint for WhatsApp delivery reports (Jazz).
    """
    raw = await request.body()
    if settings.JAZZ_WHATSAPP_WEBHOOK_SECRET:
        if not verify_hmac(raw, x_whatsapp_signature or "", settings.JAZZ_WHATSAPP_WEBHOOK_SECRET):
            raise HTTPException(status_code=403, detail="INVALID_SIGNATURE")

    payload = json.loads(raw.decode("utf-8"))
    message_id = payload.get("message_id")
    status = payload.get("status")
    
    if not message_id:
        return {"status": "ignored"}
        
    stmt = select(NotificationDispatch).where(NotificationDispatch.provider_message_id == message_id)
    dispatch = await db.scalar(stmt)
    
    if dispatch:
        if status == "delivered":
            dispatch.status = DispatchStatus.DELIVERED
            dispatch.delivered_at = datetime.now(timezone.utc)
        elif status == "read":
            dispatch.status = DispatchStatus.DELIVERED
            # We could track read_at for dispatches too if needed
            
        await db.commit()
        
    return {"status": "accepted"}
