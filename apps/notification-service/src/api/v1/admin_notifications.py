from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from sk_shared.models.notification import Notification, NotificationDispatch, NotificationTemplate, ScheduledNotification, DispatchStatus
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis, require_permissions
from src.config import settings
from src.services.notification_service import NotificationService, EVENT_CATEGORY_MAP
import logging

logger = logging.getLogger("admin_notifications")

router = APIRouter()

@router.get("/")
async def list_all_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin = Depends(require_permissions(["admin:notifications:read"]))
):
    query = select(Notification)
    if user_id:
        query = query.where(Notification.user_id == user_id)
    if status:
        query = query.where(Notification.status == status)
        
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    items = (await db.scalars(query.order_by(Notification.created_at.desc()).limit(page_size).offset((page-1)*page_size))).all()
    
    return {"items": items, "total": total}

@router.get("/stats")
async def get_notification_stats(
    db: AsyncSession = Depends(get_db),
    _admin = Depends(require_permissions(["admin:notifications:read"]))
):
    # Aggregate status counts
    status_counts = await db.execute(
        select(Notification.status, func.count(Notification.id)).group_by(Notification.status)
    )
    dispatch_counts = await db.execute(
        select(NotificationDispatch.status, func.count(NotificationDispatch.id)).group_by(NotificationDispatch.status)
    )
    
    return {
        "notifications": {r[0]: r[1] for r in status_counts},
        "dispatches": {r[0]: r[1] for r in dispatch_counts}
    }

# ── DLQ & Retries ────────────────────────────────────────────────────────────

@router.get("/dlq")
async def list_dlq_items(
    redis: RedisClient = Depends(get_redis),
    _admin = Depends(require_permissions(["admin:notifications:write"]))
):
    import json
    items = await redis.lrange(settings.NOTIFICATION_DLQ_KEY, 0, 99)
    return [json.loads(i) for i in items]

@router.post("/retry/{notification_id}")
async def retry_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _admin = Depends(require_permissions(["admin:notifications:write"]))
):
    # Reset status and re-enqueue
    notification = await db.get(Notification, notification_id)
    if not notification:
        raise HTTPException(404)
        
    notification.status = "queued"
    await db.execute(
        NotificationDispatch.__table__.update().where(
            NotificationDispatch.notification_id == notification_id,
            NotificationDispatch.status == DispatchStatus.DLQ
        ).values(status="pending", attempt_count=0)
    )
    await db.commit()
    await redis.lpush(settings.NOTIFICATION_QUEUE_KEY, str(notification_id))
    return {"status": "re-queued"}

@router.post("/dlq/retry-all")
async def retry_all_dlq(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _admin = Depends(require_permissions(["admin:notifications:write"]))
):
    """Fetch all notification IDs from DLQ and re-enqueue them."""
    import json
    items = await redis.lrange(settings.NOTIFICATION_DLQ_KEY, 0, -1)
    count = 0
    for item in items:
        try:
            data = json.loads(item)
            nid = data.get("notification_id")
            if nid:
                # Reset dispatch status in DB
                await db.execute(
                    NotificationDispatch.__table__.update().where(
                        NotificationDispatch.notification_id == nid,
                        NotificationDispatch.status == DispatchStatus.DLQ
                    ).values(status="pending", attempt_count=0)
                )
                await redis.lpush(settings.NOTIFICATION_QUEUE_KEY, str(nid))
                count += 1
        except Exception:
            continue
    
    await db.commit()
    await redis.delete(settings.NOTIFICATION_DLQ_KEY)
    return {"status": "ok", "requeued_count": count}

@router.delete("/dlq/purge")
async def purge_dlq(
    redis: RedisClient = Depends(get_redis),
    _admin = Depends(require_permissions(["admin:notifications:write"]))
):
    await redis.delete(settings.NOTIFICATION_DLQ_KEY)
    return {"status": "ok"}

# ── Templates ───────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _admin = Depends(require_permissions(["admin:notifications:read"]))
):
    templates = (await db.scalars(select(NotificationTemplate))).all()
    return templates

@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    updates: dict,
    db: AsyncSession = Depends(get_db),
    x_admin_permissions: str | None = None,
    _admin = Depends(require_permissions(["admin:notifications:write"]))
):
    from fastapi import Header
    template = await db.get(NotificationTemplate, template_id)
    if not template:
        raise HTTPException(404)

    category = EVENT_CATEGORY_MAP.get(template.event_type, "system")

    # NS-BL-07: OTP / auth templates require elevated superadmin permission.
    # Any content change to an OTP template could be used to exfiltrate codes
    # (e.g., inject a fraudulent phone number or redirect URL).
    _is_otp_template = template.event_type.startswith("auth.otp") or template.event_type in (
        "auth.otp_requested", "auth.otp_contract_sign"
    )
    if _is_otp_template:
        from src.core.dependencies import require_permissions as _rp
        _superadmin_perms = [p.strip() for p in (x_admin_permissions or "").split(",")]
        if "admin:notifications:superadmin" not in _superadmin_perms and "all_actions" not in _superadmin_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="SUPERADMIN_REQUIRED_FOR_OTP_TEMPLATES",
            )

    # Compliance Guard: If auth or compliance, deactivate and require superadmin review
    if category in ("auth", "compliance"):
        template.is_active = False
        logger.warning(
            "COMPLIANCE_GUARD_TRIGGERED",
            extra={
                "template_id": template_id,
                "event_type": template.event_type,
                "action": "DEACTIVATED_FOR_REVIEW",
            },
        )

    for k, v in updates.items():
        if k == "is_active" and category in ("auth", "compliance") and v is True:
            logger.info("COMPLIANCE_TEMPLATE_REACTIVATED", extra={"template_id": template_id})
        setattr(template, k, v)

    template.version += 1
    await db.commit()
    return template

# ── Scheduled ───────────────────────────────────────────────────────────────

@router.get("/scheduled")
async def list_scheduled(
    db: AsyncSession = Depends(get_db),
    _admin = Depends(require_permissions(["admin:notifications:read"]))
):
    scheduled = (await db.scalars(select(ScheduledNotification).where(ScheduledNotification.fired_at == None))).all()
    return scheduled

@router.delete("/scheduled/{scheduled_id}")
async def cancel_scheduled(
    scheduled_id: int,
    db: AsyncSession = Depends(get_db),
    _admin = Depends(require_permissions(["admin:notifications:write"]))
):
    from datetime import datetime, timezone
    scheduled = await db.get(ScheduledNotification, scheduled_id)
    if not scheduled:
        raise HTTPException(404)
    if scheduled.fired_at:
        raise HTTPException(400, detail="ALREADY_FIRED")
    
    scheduled.cancelled_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled"}
