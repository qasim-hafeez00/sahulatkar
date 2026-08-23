from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis, get_current_user_id, require_internal_key
from src.services.notification_service import NotificationService
from src.services.preference_service import PreferenceService
from src.schemas.notifications import (
    NotificationInboxResponse, NotificationPreferencesResponse, 
    PreferenceUpdateRequest, InternalNotificationRequest, 
    OTPRequest, BulkNotificationRequest
)

router = APIRouter()
internal_router = APIRouter()

# ── Customer Endpoints ───────────────────────────────────────────────────────

@router.get("/", response_model=NotificationInboxResponse)
async def list_notifications(
    user_id: int = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    ns = NotificationService(db=db, redis=redis)
    items, total, unread = await ns.get_user_notifications(
        user_id=user_id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
        category=category
    )
    return {
        "items": items,
        "total": total,
        "unread_count": unread,
        "page": page,
        "page_size": page_size
    }

@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    ns = NotificationService(db=db, redis=redis)
    success = await ns.mark_read(notification_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="NOTIFICATION_NOT_FOUND")
    return {"status": "ok"}

@router.post("/read-all")
async def mark_all_notifications_read(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    ns = NotificationService(db=db, redis=redis)
    count = await ns.mark_all_read(user_id)
    return {"status": "ok", "marked_read": count}

@router.get("/unread-count")
async def get_unread_count(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    ns = NotificationService(db=db, redis=redis)
    _, _, unread = await ns.get_user_notifications(user_id=user_id, page_size=1, unread_only=True)
    return {"unread_count": unread}

@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_preferences(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ps = PreferenceService(db=db)
    prefs = await ps.get_all_preferences(user_id)
    # Map to schema (adding category labels etc would happen here)
    return {"preferences": prefs}

@router.put("/preferences")
async def update_preferences(
    req: PreferenceUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ps = PreferenceService(db=db)
    results = await ps.update_preferences(user_id, [p.model_dump() for p in req.preferences])
    return {"status": "ok", "updated": len(results)}

@router.post("/unsubscribe")
async def global_unsubscribe(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ps = PreferenceService(db=db)
    await ps.toggle_global_unsubscribe(user_id, True)
    return {"status": "unsubscribed", "message": "You have been globally unsubscribed from all non-essential notifications."}

# ── Internal Endpoints ───────────────────────────────────────────────────────

@internal_router.post("/send")
async def internal_send_notification(
    req: InternalNotificationRequest,
    _auth = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    ns = NotificationService(db=db, redis=redis)
    notification = await ns.create_notification(
        user_id=req.user_id,
        event_type=req.event_type,
        template_vars=req.template_vars,
        idempotency_key=req.idempotency_key,
        source_reference=req.source_reference,
        priority=req.priority,
        channel_override=[c.value for c in req.channels] if req.channels else None
    )
    return {"status": "queued", "notification_id": notification.id}

@internal_router.post("/otp")
async def internal_send_otp(
    req: OTPRequest,
    background_tasks: BackgroundTasks,
    _auth = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Specialized OTP dispatch with strict rate limiting and bypassing preferences."""
    ns = NotificationService(db=db, redis=redis)
    result = await ns.send_otp(
        phone=req.phone,
        otp_code=req.otp_code,
        purpose=req.purpose,
        expires_in_seconds=req.expires_in_seconds,
        channels=[c.value for c in req.channels] if req.channels else None,
    )
    
    if result["status"] == "rate_limited":
        raise HTTPException(status_code=429, detail=result["detail"])
        
    return result

@internal_router.post("/bulk")
async def internal_send_bulk(
    req: BulkNotificationRequest,
    _auth = Depends(require_internal_key),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    ns = NotificationService(db=db, redis=redis)
    stats = await ns.create_bulk_notifications(
        event_type=req.event_type,
        notifications=[n.model_dump() for n in req.notifications]
    )
    return stats
