from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.audit import record_audit_event
from src.core.dependencies import get_current_admin, get_db, get_redis, RequirePermission
from src.schemas.kyc import AdminKycDecisionRequest, KycVerificationResponse, KycQueueItemResponse
from src.services.kyc_queue import KycQueueService
from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient

router = APIRouter(prefix="/admin/kyc", tags=["Admin KYC"])


@router.get("/queue", response_model=list[KycQueueItemResponse])
async def get_queue(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    """Return all pending, unclaimed KYC review items with pagination."""
    offset = (page - 1) * limit
    service = KycQueueService(db, redis_client)
    items = await service.get_queue(offset=offset, limit=limit)
    
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    res = []
    for item in items:
        # Assuming created_at is naive UTC from DB, make it aware
        created_aware = item.created_at.replace(tzinfo=timezone.utc) if item.created_at.tzinfo is None else item.created_at
        breached = (now - created_aware).total_seconds() > 48 * 3600
        # Create response dict/model manually or use model_copy
        model = KycQueueItemResponse.model_validate(item)
        model.sla_breached = breached
        res.append(model)
        
    return res


@router.post("/{queue_id}/claim", status_code=status.HTTP_200_OK)
async def claim_queue_item(
    queue_id: int,
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    """Claim a KYC queue item for review."""
    service = KycQueueService(db, redis_client)
    try:
        return await service.claim(queue_id, current_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{queue_id}/decision", response_model=KycVerificationResponse)
async def submit_decision(
    queue_id: int,
    request: AdminKycDecisionRequest,
    http_request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    """Approve or reject a KYC submission."""
    if not request.approved and not request.rejection_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rejection_reason is required when rejecting.",
        )
    service = KycQueueService(db, redis_client)
    try:
        kyc = await service.process_decision(
            queue_id, current_admin.id, request.approved, request.rejection_reason
        )
        await record_audit_event(
            db=db,
            request=http_request,
            admin_user_id=current_admin.id,
            module="kyc",
            action="admin_decision",
            target_id=kyc.id,
            changes={
                "approved": request.approved,
                "rejection_reason": request.rejection_reason,
                "queue_id": queue_id,
            },
        )
        await db.commit()
        return kyc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# ── MISS-13: Admin-triggered KYC Re-verification ─────────────────────────────

@router.post("/{user_id}/trigger-reverification")
async def trigger_kyc_reverification(
    user_id: int,
    http_request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
) -> dict:
    """Reset a user's KYC to PENDING and notify them to re-submit documents."""
    import json
    from datetime import datetime, timezone
    from sk_shared.models.auth import User
    from sk_shared.models.kyc import UserKycVerification
    from sk_shared.constants import QueueName

    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    old_status = user.status
    user.status = "pending_kyc"

    try:
        existing = await db.scalar(
            select(UserKycVerification).where(
                UserKycVerification.user_id == user_id,
                UserKycVerification.deleted_at.is_(None),
            ).order_by(UserKycVerification.created_at.desc())
        )
        if existing:
            existing.deleted_at = datetime.now(timezone.utc)
    except Exception:
        pass

    await record_audit_event(
        db=db,
        request=http_request,
        admin_user_id=current_admin.id,
        module="admin_kyc",
        action="trigger_reverification",
        target_id=user_id,
        changes={"old_status": old_status, "new_status": "pending_kyc"},
    )

    if hasattr(redis_client, "redis"):
        notification = json.dumps({
            "event": "kyc.reverification_required",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await redis_client.redis.lpush(QueueName.NOTIFICATION_SMS, notification)

    await db.commit()
    return {"user_id": user_id, "status": "pending_kyc", "reverification_triggered": True}
