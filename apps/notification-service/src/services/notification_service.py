from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.notification import (
    Notification, NotificationDispatch, NotificationStatus,
    DispatchStatus
)
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.services.preference_service import PreferenceService, NON_OPTOUT_CATEGORIES
from src.services.template_service import TemplateService
import logging
from src.dispatchers.sms_dispatcher import JazzSMSDispatcher
from src.dispatchers.whatsapp_dispatcher import JazzWhatsAppDispatcher
from src.dispatchers.push_dispatcher import FCMPushDispatcher
from src.dispatchers.email_dispatcher import SendGridEmailDispatcher
import time
from src.core.middleware import (
    notifications_dispatched_total, 
    notification_dispatch_latency_seconds
)

logger = logging.getLogger("notification_service")

DISPATCHERS = {
    "sms": JazzSMSDispatcher(),
    "whatsapp": JazzWhatsAppDispatcher(),
    "push": FCMPushDispatcher(),
    "email": SendGridEmailDispatcher(),
}

EVENT_CHANNEL_MATRIX: dict[str, dict] = {
    "auth.otp_requested":               {"channels": ["sms"], "priority": "critical"},
    "auth.otp_contract_sign":            {"channels": ["sms"], "priority": "critical"},
    "kyc.submitted":                     {"channels": ["whatsapp", "push"], "priority": "high"},
    "kyc.approved":                      {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "kyc.rejected":                      {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "kyc.waitlisted":                    {"channels": ["whatsapp", "push"], "priority": "high"},
    "credit.assessed.approved":          {"channels": ["whatsapp", "push"], "priority": "high"},
    "credit.assessed.rejected":          {"channels": ["whatsapp", "push"], "priority": "high"},
    "credit.limit_increased":            {"channels": ["whatsapp", "push"], "priority": "normal"},
    "product.extracted":                 {"channels": ["push"], "priority": "normal"},
    "order.offer_ready":                 {"channels": ["whatsapp", "push"], "priority": "high"},
    "contract.wakalah_ready":            {"channels": ["sms", "whatsapp", "push", "email"], "priority": "high"},
    "contract.murabaha_ready":           {"channels": ["sms", "whatsapp", "push", "email"], "priority": "high"},
    "contract.signed":                   {"channels": ["whatsapp", "push", "email"], "priority": "high"},
    "payment.down_payment_initiated":    {"channels": ["sms", "push"], "priority": "high"},
    "payment.down_payment_confirmed":    {"channels": ["sms", "whatsapp", "push", "email"], "priority": "high"},
    "payment.down_payment_failed":       {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "order.vcn_issued":                  {"channels": ["push"], "priority": "normal"},
    "order.checkout_completed":          {"channels": ["whatsapp", "push", "email"], "priority": "high"},
    "order.checkout_failed":             {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "delivery.status_changed":           {"channels": ["whatsapp", "push"], "priority": "normal"},
    "delivery.confirmed":                {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "delivery.returned":                 {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "billing.installment_due_d3":        {"channels": ["whatsapp", "push"], "priority": "normal"},
    "billing.installment_due_d1":        {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "billing.installment_due_today":     {"channels": ["sms", "push"], "priority": "high"},
    "billing.installment_paid":          {"channels": ["whatsapp", "push"], "priority": "normal"},
    "billing.installment_failed":        {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "billing.installment_overdue_d1":    {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "billing.installment_overdue_d7":    {"channels": ["sms", "whatsapp"], "priority": "high"},
    "billing.installment_overdue_d14":   {"channels": ["sms", "whatsapp"], "priority": "high"},
    "billing.late_fee_applied":          {"channels": ["sms", "whatsapp", "push", "email"], "priority": "high", "is_compliance": True},
    "billing.late_fee_charity_allocated":{"channels": ["whatsapp", "push"], "priority": "normal", "is_compliance": True},
    "billing.loan_fully_repaid":         {"channels": ["whatsapp", "push", "email"], "priority": "high"},
    # ── Missing integration events (NS-BL-05 / Section 6.4) ─────────────────
    "order.cancelled":                   {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "vcn.expired":                       {"channels": ["push", "sms"], "priority": "high"},
    "payment.failed":                    {"channels": ["sms", "whatsapp", "push"], "priority": "high"},
    "kyc.documents_needed":              {"channels": ["whatsapp", "push"], "priority": "high"},
    "credit.limit_changed":              {"channels": ["whatsapp", "push"], "priority": "normal"},
}

EVENT_CATEGORY_MAP: dict[str, str] = {
    "auth.otp_requested": "auth",
    "auth.otp_contract_sign": "auth",
    "kyc.submitted": "kyc", "kyc.approved": "kyc", "kyc.rejected": "kyc",
    "credit.assessed.approved": "credit", "credit.assessed.rejected": "credit",
    "credit.limit_increased": "credit",
    "product.extracted": "order", "order.offer_ready": "order",
    "contract.wakalah_ready": "contract", "contract.murabaha_ready": "contract",
    "contract.signed": "contract",
    "payment.down_payment_initiated": "payment",
    "payment.down_payment_confirmed": "payment",
    "payment.down_payment_failed": "payment",
    "order.vcn_issued": "order", "order.checkout_completed": "order",
    "order.checkout_failed": "order",
    "delivery.status_changed": "delivery", "delivery.confirmed": "delivery",
    "delivery.returned": "delivery",
    "billing.installment_due_d3": "billing",
    "billing.installment_due_d1": "billing",
    "billing.installment_due_today": "billing",
    "billing.installment_paid": "billing",
    "billing.installment_failed": "billing",
    "billing.installment_overdue_d1": "billing",
    "billing.installment_overdue_d7": "billing",
    "billing.installment_overdue_d14": "billing",
    "billing.late_fee_applied": "compliance",
    "billing.late_fee_charity_allocated": "compliance",
    "billing.loan_fully_repaid": "billing",
    # Missing integration events
    "order.cancelled": "order",
    "vcn.expired": "order",
    "payment.failed": "payment",
    "kyc.documents_needed": "kyc",
    "credit.limit_changed": "credit",
}

class NotificationService:
    def __init__(self, db: AsyncSession, redis: RedisClient):
        self.db = db
        self.redis = redis
        self.template_service = TemplateService()
        self.preference_service = PreferenceService(db=db)

    async def create_notification(
        self,
        *,
        user_id: int,
        event_type: str,
        template_vars: dict,
        idempotency_key: str,
        source_reference: Optional[str] = None,
        channel_override: Optional[list[str]] = None,
        priority: Optional[str] = None,
    ) -> Notification:
        existing = await self.db.scalar(
            select(Notification).where(Notification.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        matrix_config = EVENT_CHANNEL_MATRIX.get(event_type, {})
        notification_priority = priority or matrix_config.get("priority", "normal")
        category = EVENT_CATEGORY_MAP.get(event_type, "system")
        is_compliance = matrix_config.get("is_compliance", False) or category in ("auth", "compliance")

        requested_channels = channel_override or matrix_config.get("channels", ["push"])
        
        if not is_compliance and category not in NON_OPTOUT_CATEGORIES:
            requested_channels = await self.preference_service.filter_channels(
                user_id=user_id,
                category=category,
                requested_channels=requested_channels,
            )

        if notification_priority != "critical":
            requested_channels = await self._apply_rate_limits(
                user_id=user_id,
                channels=requested_channels,
            )

        title, body = self.template_service.render(
            event_type=event_type,
            channel="push",
            template_vars=template_vars,
        )

        notification = Notification(
            user_id=user_id,
            source_event=event_type,
            source_reference=source_reference,
            category=category,
            priority=notification_priority,
            title=title,
            body=body,
            status=NotificationStatus.QUEUED,
            idempotency_key=idempotency_key,
            channels_requested=requested_channels,
            template_vars=template_vars,
        )
        self.db.add(notification)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return await self.db.scalar(
                select(Notification).where(Notification.idempotency_key == idempotency_key)
            )

        for channel in requested_channels:
            self.db.add(NotificationDispatch(
                notification_id=notification.id,
                channel=channel,
                status="pending",
            ))

        await self.db.commit()
        await self.db.refresh(notification)

        await self._enqueue(notification.id)
        return notification

    async def send_otp(
        self,
        *,
        phone: str,
        otp_code: str,
        purpose: str,
        expires_in_seconds: int = 300,
        channels: Optional[list[str]] = None,
    ) -> dict:
        """
        Specialized handler for OTPs. Bypasses standard queue and preferences.
        Uses a dedicated rate limit namespace: sk:ratelimit:otp:{phone}
        """
        # 0. Basic Validation
        if not phone or len(phone) < 10:
            return {"status": "error", "detail": "INVALID_PHONE_NUMBER"}

        # 1. Rate Limit Check
        is_allowed = await self._apply_otp_rate_limit(phone)
        if not is_allowed:
            from src.core.middleware import otp_rate_limited_total
            otp_rate_limited_total.labels(phone_prefix=phone[-3:]).inc()
            return {"status": "rate_limited", "detail": "TOO_MANY_OTP_REQUESTS"}

        # 2. Find User (Optional - OTPs might be for registration)
        from sk_shared.models.auth import User
        user = await self.db.scalar(select(User).where(User.phone == phone))
        # Use 0 as a sentinel for unregistered-phone OTPs.
        # NEVER fall back to user_id=1 (super admin) — that pollutes the audit trail.
        # Dispatch destination is resolved via template_vars["destination_phone"],
        # so the real DB user record is not needed for delivery.
        user_id = user.id if user else 0

        # 3. Create Notification Record
        event_type = f"auth.otp_{purpose}"
        if event_type not in EVENT_CATEGORY_MAP:
            event_type = "auth.otp_requested"

        {
            "otp": otp_code,
            "expires_min": expires_in_seconds // 60,
            "purpose": purpose.replace("_", " ")
        }
        
        # We use a simplified rendering here to avoid logging the OTP
        title = "SahulatKar OTP"
        body = f"Your SahulatKar OTP is {otp_code}. Valid for {expires_in_seconds // 60} minutes. Do not share this code."

        # Support multiple channels for OTP (e.g. SMS + WhatsApp fallback)
        requested_channels = channels or ["sms"]

        notification = Notification(
            user_id=user_id,
            source_event=event_type,
            category="auth",
            priority="critical",
            title=title,
            body=body,
            status=NotificationStatus.QUEUED,
            idempotency_key=f"otp-{phone}-{datetime.now(timezone.utc).timestamp()}",
            channels_requested=requested_channels,
            template_vars={
                "purpose": purpose,
                "destination_phone": phone
            }, # Don't store OTP in template_vars for security
        )
        self.db.add(notification)

        await self.db.flush()

        for channel in requested_channels:
            dispatch = NotificationDispatch(
                notification_id=notification.id,
                channel=channel,
                status="pending",
            )
            self.db.add(dispatch)
        
        await self.db.commit()

        # 4. Dispatch Immediately (caller should wrap in BackgroundTasks)
        await self.dispatch_notification(notification.id)
        
        from src.core.middleware import otp_sent_total
        otp_sent_total.labels(purpose=purpose).inc()
        
        return {"status": "sent", "notification_id": notification.id}

    async def _apply_otp_rate_limit(self, phone: str) -> bool:
        key_h = f"sk:ratelimit:otp:h:{phone}"
        key_d = f"sk:ratelimit:otp:d:{phone}"
        
        limit_h = settings.OTP_SMS_RATE_LIMIT_PER_PHONE_PER_HOUR
        limit_d = settings.OTP_SMS_RATE_LIMIT_PER_PHONE_PER_DAY
        
        try:
            # Hourly limit
            count_h = await self.redis.incr(key_h)
            if count_h == 1:
                await self.redis.expire(key_h, 3600)
            
            # Daily limit
            count_d = await self.redis.incr(key_d)
            if count_d == 1:
                await self.redis.expire(key_d, 86400)
                
            return count_h <= limit_h and count_d <= limit_d
        except Exception:
            return True

    async def create_bulk_notifications(
        self,
        *,
        event_type: str,
        notifications: list[dict],
    ) -> dict:
        """Bulk creation for scheduled reminders and large sweeps."""
        stats = {"accepted": 0, "skipped_duplicate": 0, "failed": 0, "queued_notification_ids": []}
        
        # Process in batches of 50 to avoid long-running transactions
        BATCH_SIZE = 50
        for i in range(0, len(notifications), BATCH_SIZE):
            batch = notifications[i:i + BATCH_SIZE]
            for item in batch:
                try:
                    if not item.get("user_id") or not item.get("idempotency_key"):
                        stats["failed"] += 1
                        continue

                    notif = await self.create_notification(
                        user_id=item["user_id"],
                        event_type=event_type,
                        template_vars=item.get("template_vars", {}),
                        idempotency_key=item["idempotency_key"],
                        source_reference=item.get("source_reference"),
                    )
                    
                    if notif.id not in stats["queued_notification_ids"]:
                        stats["accepted"] += 1
                        stats["queued_notification_ids"].append(notif.id)
                    else:
                        stats["skipped_duplicate"] += 1
                except Exception as e:
                    logger.error(f"Bulk item failed: {e}")
                    stats["failed"] += 1
            
            # Flush periodically if needed, though create_notification commits each time
            # For pure bulk we might want to refactor create_notification for batching
            
        return stats

    async def _apply_rate_limits(
        self, user_id: int, channels: list[str]
    ) -> list[str]:
        allowed = []
        limits = {
            "sms": (settings.SMS_RATE_LIMIT_PER_USER_PER_HOUR, 3600),
            "whatsapp": (settings.WHATSAPP_RATE_LIMIT_PER_USER_PER_HOUR, 3600),
            "push": (settings.PUSH_RATE_LIMIT_PER_USER_PER_HOUR, 3600),
            "email": (settings.EMAIL_RATE_LIMIT_PER_USER_PER_DAY, 86400),
        }
        for ch in channels:
            limit, window = limits.get(ch, (100, 3600))
            key = f"sk:ratelimit:notif:{user_id}:{ch}"
            # For testing, pretend no rate limit is hit if redis is fake
            try:
                count = await self.redis.incr(key)
                if count == 1:
                    await self.redis.expire(key, window)
                if count <= limit:
                    allowed.append(ch)
            except Exception:
                allowed.append(ch)
        return allowed

    async def _enqueue(self, notification_id: int) -> None:
        try:
            await self.redis.lpush(
                settings.NOTIFICATION_QUEUE_KEY,
                str(notification_id),
            )
        except Exception:
            pass

    async def get_user_notifications(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
        category: Optional[str] = None,
    ) -> tuple[list[Notification], int, int]:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        if category:
            query = query.where(Notification.category == category)
        
        # Total count
        total = await self.db.scalar(
            select(func.count(Notification.id)).where(Notification.user_id == user_id)
        )
        
        # Unread count
        unread = await self.db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False)
            )
        )
        
        items = (await self.db.scalars(
            query.order_by(Notification.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )).all()
        
        return items, total or 0, unread or 0

    async def mark_read(self, notification_id: int, user_id: int) -> bool:
        notification = await self.db.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        if notification is None:
            return False
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await self.db.commit()
        return True

    async def mark_all_read(self, user_id: int) -> int:
        from sqlalchemy import update
        stmt = update(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False)
        ).values(
            is_read=True,
            read_at=datetime.now(timezone.utc)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def dispatch_notification(self, notification_id: int) -> None:
        """Process a single notification: dispatch all pending channels."""
        notification = await self.db.get(Notification, notification_id)
        # NOTE: DELIVERED means "at least one channel delivered" (see NotificationStatus),
        # not "every channel is done" — a retry re-enqueue for this notification_id can
        # arrive while the aggregate status is already DELIVERED because a different
        # channel succeeded first. Only CANCELLED is a genuine hard-stop here; whether
        # there's still work to do is decided below by the per-dispatch-row query.
        if notification is None or notification.status == NotificationStatus.CANCELLED:
            return

        dispatches = (await self.db.scalars(
            select(NotificationDispatch).where(
                NotificationDispatch.notification_id == notification_id,
                NotificationDispatch.status.in_(["pending", "retrying"]),
            )
        )).all()

        if not dispatches:
            return

        notification.status = NotificationStatus.DISPATCHING
        await self.db.flush()

        any_success = False

        for dispatch in dispatches:
            channel = dispatch.channel
            dispatcher = DISPATCHERS.get(channel)
            if dispatcher is None:
                continue

            destination = await self._get_user_destination(notification, channel)
            if not destination:
                dispatch.status = DispatchStatus.FAILED
                dispatch.failure_reason = "NO_DESTINATION"
                dispatch.failed_at = datetime.now(timezone.utc)
                continue

            try:
                # Use stored template_vars for channel-specific rendering
                rendered_title, rendered_body = self.template_service.render(
                    event_type=notification.source_event,
                    channel=channel,
                    template_vars=notification.template_vars,
                )
                content = rendered_body
                subject = rendered_title
            except Exception as e:
                logger.error("Template rendering failed", extra={"notification_id": notification_id, "channel": channel, "error": str(e)})
                content = notification.body
                subject = notification.title

            dispatch.attempt_count += 1
            dispatch.rendered_content = content[:500]

            start_time = time.time()
            result = await dispatcher.send(
                destination=destination,
                content=content,
                subject=subject,
                notification_id=notification_id,
            )
            duration = time.time() - start_time

            if result.success:
                dispatch.status = DispatchStatus.SENT
                dispatch.provider_message_id = result.provider_message_id
                dispatch.provider_name = result.provider_name
                dispatch.sent_at = datetime.now(timezone.utc)
                any_success = True
                
                notifications_dispatched_total.labels(
                    channel=channel, 
                    event_type=notification.source_event, 
                    result="success"
                ).inc()
                notification_dispatch_latency_seconds.labels(
                    channel=channel, 
                    provider=result.provider_name
                ).observe(duration)
            else:
                res_type = "failed"
                if not result.should_retry or dispatch.attempt_count >= settings.MAX_DISPATCH_RETRIES:
                    dispatch.status = DispatchStatus.DLQ if result.should_retry else DispatchStatus.FAILED
                    dispatch.failure_reason = result.failure_reason
                    dispatch.failed_at = datetime.now(timezone.utc)
                    if dispatch.status == DispatchStatus.DLQ:
                        await self._push_to_dlq(notification_id, dispatch.id, result.failure_reason)
                        res_type = "dlq"
                else:
                    dispatch.status = DispatchStatus.RETRYING
                    dispatch.failure_reason = result.failure_reason
                    delay = settings.RETRY_BACKOFF_BASE_SECONDS * (3 ** (dispatch.attempt_count - 1))
                    dispatch.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    res_type = "retrying"
                
                notifications_dispatched_total.labels(
                    channel=channel, 
                    event_type=notification.source_event, 
                    result=res_type
                ).inc()

        # Derive the aggregate status from ALL dispatch rows (not just the ones
        # processed in this call) — otherwise a later retry attempt on a channel
        # that fails again would overwrite a previously-successful DELIVERED
        # status back to FAILED, even though an earlier channel already delivered.
        all_dispatches = (await self.db.scalars(
            select(NotificationDispatch).where(
                NotificationDispatch.notification_id == notification_id,
            )
        )).all()
        if any_success or any(d.status in (DispatchStatus.SENT, DispatchStatus.DELIVERED) for d in all_dispatches):
            notification.status = NotificationStatus.DELIVERED
        elif any(d.status in (DispatchStatus.PENDING, DispatchStatus.RETRYING) for d in all_dispatches):
            notification.status = NotificationStatus.DISPATCHING
        else:
            notification.status = NotificationStatus.FAILED
        await self.db.commit()

    async def _get_user_destination(self, notification: Notification, channel: str) -> Optional[str]:
        # Check template_vars for explicit overrides (e.g., OTP for unregistered users)
        if notification.template_vars:
            if channel in ("sms", "whatsapp") and "destination_phone" in notification.template_vars:
                return notification.template_vars["destination_phone"]
            if channel == "email" and "destination_email" in notification.template_vars:
                return notification.template_vars["destination_email"]

        from sk_shared.models.auth import User
        user = await self.db.get(User, notification.user_id)
        if user is None:
            return None
        if channel in ("sms", "whatsapp"):
            return user.phone
        if channel == "push":
            return getattr(user, "fcm_token", None)
        if channel == "email":
            return getattr(user, "email", None)
        return None

    async def _push_to_dlq(self, notification_id: int, dispatch_id: int, reason: str) -> None:
        import json
        await self.redis.lpush(settings.NOTIFICATION_DLQ_KEY, json.dumps({
            "notification_id": notification_id,
            "dispatch_id": dispatch_id,
            "reason": reason,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }))
