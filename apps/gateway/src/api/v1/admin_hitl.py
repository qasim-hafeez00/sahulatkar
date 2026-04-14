from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser

from src.core.dependencies import get_current_admin, get_db
from src.schemas.hitl import HitlListResponse, HitlQueueItemResponse, HitlResolveRequest, HitlStatusResponse
from src.services.hitl_queue import HitlQueueService


router = APIRouter(prefix="/admin/hitl", tags=["Admin HITL"])


def _serialize(item) -> HitlQueueItemResponse:
    return HitlQueueItemResponse(
        id=item.id,
        uuid=item.uuid,
        order_id=item.order_id,
        execution_id=item.execution_id,
        priority=item.priority,
        assigned_to=item.assigned_to,
        status=item.status,
        failure_reason=item.failure_reason,
        screenshot_s3=item.screenshot_s3,
        resolution=item.resolution,
        claimed_at=item.claimed_at,
        in_progress_at=item.in_progress_at,
        resolved_at=item.resolved_at,
        sla_deadline=item.sla_deadline,
    )


@router.get("/queue", response_model=HitlListResponse)
async def list_hitl_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    service = HitlQueueService(db)
    items = await service.list_queue(status=status_filter)
    return HitlListResponse(items=[_serialize(item) for item in items])


@router.get("/queue/{queue_id}", response_model=HitlQueueItemResponse)
async def get_hitl_queue_item(
    queue_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    service = HitlQueueService(db)
    item = await service.get_item(queue_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HITL_ITEM_NOT_FOUND")
    return _serialize(item)


@router.post("/{queue_id}/claim", response_model=HitlQueueItemResponse)
async def claim_hitl_item(
    queue_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    service = HitlQueueService(db)
    try:
        item = await service.claim(queue_id, current_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _serialize(item)


@router.post("/{queue_id}/start", response_model=HitlStatusResponse)
async def start_hitl_item(
    queue_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    service = HitlQueueService(db)
    try:
        item = await service.start(queue_id, current_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HitlStatusResponse(status=item.status)


@router.post("/{queue_id}/resolve", response_model=HitlStatusResponse)
async def resolve_hitl_item(
    queue_id: int,
    request: HitlResolveRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    service = HitlQueueService(db)
    try:
        item = await service.resolve(queue_id, current_admin.id, request.resolution)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HitlStatusResponse(status=item.status)


@router.post("/{queue_id}/cancel", response_model=HitlStatusResponse)
async def cancel_hitl_item(
    queue_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    service = HitlQueueService(db)
    try:
        item = await service.cancel(queue_id, current_admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return HitlStatusResponse(status=item.status)