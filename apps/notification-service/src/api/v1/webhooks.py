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


def _verify_sendgrid_signature(
    raw_body: bytes,
    signature: str,
    timestamp: str,
    public_key_b64: str,
) -> bool:
    """
    NS-BL-01: Verify SendGrid Event Webhook ECDSA-P256 signature.

    SendGrid signs events with a 256-bit EC key (P-256 curve / secp256r1).
    The signed payload is: timestamp + raw_body (no separator).
    Header: X-Twilio-Email-Event-Webhook-Signature  (base64 DER)
            X-Twilio-Email-Event-Webhook-Timestamp
    Public key:  stored as base64-encoded DER (SPKI format) in settings.
    """
    try:
        import base64
        from cryptography.hazmat.primitives.asymmetric.ec import (
            ECDSA, EllipticCurvePublicKey,
        )
        from cryptography.hazmat.primitives.hashes import SHA256
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        from cryptography.exceptions import InvalidSignature

        public_key_der = base64.b64decode(public_key_b64)
        public_key: EllipticCurvePublicKey = load_der_public_key(public_key_der)  # type: ignore[assignment]
        sig_bytes = base64.b64decode(signature)
        payload_to_verify = (timestamp.encode() + raw_body)
        public_key.verify(sig_bytes, payload_to_verify, ECDSA(SHA256()))
        return True
    except InvalidSignature:
        return False
    except Exception:
        # Decoding / import error — treat as invalid
        return False


@router.post("/sendgrid")
async def sendgrid_webhook(
    request: Request,
    x_twilio_email_event_webhook_signature: str | None = Header(default=None),
    x_twilio_email_event_webhook_timestamp: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Process SendGrid Event Webhooks for delivery and unsubscribe tracking.

    NS-BL-01: Signature verification is enforced when SENDGRID_WEBHOOK_SECRET is
    configured (base64-encoded DER public key from SendGrid dashboard).
    Without a secret configured the endpoint accepts all requests but logs a warning.
    """
    import logging
    _log = logging.getLogger("sendgrid_webhook")

    raw = await request.body()

    if settings.SENDGRID_WEBHOOK_SECRET:
        sig = x_twilio_email_event_webhook_signature or ""
        ts  = x_twilio_email_event_webhook_timestamp  or ""
        if not sig or not ts:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MISSING_SENDGRID_SIGNATURE_HEADERS",
            )
        if not _verify_sendgrid_signature(raw, sig, ts, settings.SENDGRID_WEBHOOK_SECRET):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="INVALID_SENDGRID_SIGNATURE",
            )
    else:
        _log.warning(
            "SendGrid webhook received without signature verification — "
            "set SENDGRID_WEBHOOK_SECRET to enforce ECDSA validation."
        )

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="INVALID_SENDGRID_PAYLOAD") from exc

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

    NS-BL-06: WhatsApp delivery states have distinct semantics:
      sent      — message accepted by WhatsApp servers
      delivered — message reached the recipient device  →  set DELIVERED
      read      — recipient opened the message          →  update read_at only
    Only "delivered" should transition dispatch status to DELIVERED.
    """
    raw = await request.body()
    if settings.JAZZ_WHATSAPP_WEBHOOK_SECRET:
        if not verify_hmac(raw, x_whatsapp_signature or "", settings.JAZZ_WHATSAPP_WEBHOOK_SECRET):
            raise HTTPException(status_code=403, detail="INVALID_SIGNATURE")

    payload = json.loads(raw.decode("utf-8"))
    message_id = payload.get("message_id")
    wa_status = payload.get("status")
    
    if not message_id:
        return {"status": "ignored"}
        
    stmt = select(NotificationDispatch).where(NotificationDispatch.provider_message_id == message_id)
    dispatch = await db.scalar(stmt)
    
    if dispatch:
        if wa_status == "delivered":
            # Only "delivered" → device actually received the message
            dispatch.status = DispatchStatus.DELIVERED
            dispatch.delivered_at = datetime.now(timezone.utc)
        elif wa_status == "read":
            # "read" means the user opened it — this does NOT mean delivery just happened.
            # We do NOT overwrite status here; if already DELIVERED, that's correct.
            # Track read time if the column exists (best-effort).
            if hasattr(dispatch, "read_at"):
                dispatch.read_at = datetime.now(timezone.utc)
        elif wa_status == "failed":
            dispatch.status = DispatchStatus.FAILED
            dispatch.failed_at = datetime.now(timezone.utc)
            dispatch.failure_reason = payload.get("error_data", {}).get("details", "WA_DELIVERY_FAILED") \
                if isinstance(payload.get("error_data"), dict) else "WA_DELIVERY_FAILED"
            
        await db.commit()
        
    return {"status": "accepted"}
