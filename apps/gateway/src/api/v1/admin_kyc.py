from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_admin, get_db, get_redis
from src.schemas.kyc import AdminKycDecisionRequest, KycVerificationResponse
from src.services.kyc_queue import KycQueueService
from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient

router = APIRouter(prefix="/admin/kyc", tags=["Admin KYC"])


@router.get("/queue")
async def get_queue(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: RedisClient = Depends(get_redis),
):
    """Return all pending, unclaimed KYC review items."""
    service = KycQueueService(db, redis_client)
    return await service.get_queue()


@router.post("/{queue_id}/claim", status_code=status.HTTP_200_OK)
async def claim_queue_item(
    queue_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
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
    current_admin: AdminUser = Depends(get_current_admin),
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
        return kyc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
