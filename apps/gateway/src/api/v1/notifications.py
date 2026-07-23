from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.models.notification import Notification
from src.core.dependencies import get_current_user, get_db
from src.schemas.notifications import NotificationItem, NotificationListResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        base = base.where(Notification.is_read.is_(False))

    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    unread_count = await db.scalar(
        select(func.count()).select_from(
            select(Notification.id)
            .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
            .subquery()
        )
    )

    rows = (
        await db.execute(
            base.order_by(Notification.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars().all()

    return NotificationListResponse(
        items=[NotificationItem.model_validate(n) for n in rows],
        unread_count=int(unread_count or 0),
        total=int(total or 0),
    )


@router.post("/{notification_id}/read", response_model=NotificationItem)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOTIFICATION_NOT_FOUND")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)

    return NotificationItem.model_validate(notification)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return
