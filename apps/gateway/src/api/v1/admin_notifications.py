"""Admin Notification Center — Phase 4 thin module."""
from __future__ import annotations

import json
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName
from sk_shared.models.auth import AdminUser
from sk_shared.models.notification import Notification, NotificationTemplate
from sk_shared.redis_client import RedisClient
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/notifications", tags=["Admin Notifications"])

_CHANNEL_QUEUES = {
    "sms": QueueName.NOTIFICATION_SMS,
    "push": QueueName.NOTIFICATION_PUSH,
    "email": QueueName.NOTIFICATION_EMAIL,
    "whatsapp": QueueName.NOTIFICATION_WHATSAPP,
}


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("")
async def list_notifications(
    category: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    query = select(Notification)
    if category:
        query = query.where(Notification.category == category)
    if status_filter:
        query = query.where(Notification.status == status_filter)

    rows = (
        await db.execute(query.order_by(Notification.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    total = int(await db.scalar(select(func.count(Notification.id))) or 0)

    return {
        "items": [
            {
                "id": n.id,
                "user_id": n.user_id,
                "category": n.category,
                "priority": n.priority,
                "title": n.title,
                "body": n.body,
                "status": n.status,
                "channels_requested": n.channels_requested,
                "is_read": n.is_read,
                "created_at": _iso(n.created_at),
            }
            for n in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/summary")
async def notifications_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status_rows = (
        await db.execute(text("SELECT status, COUNT(*) AS cnt FROM notifications GROUP BY status"))
    ).mappings().all()
    dispatch_rows = (
        await db.execute(text("SELECT channel, status, COUNT(*) AS cnt FROM notification_dispatches GROUP BY channel, status"))
    ).mappings().all()
    return {
        "by_status": {r["status"]: int(r["cnt"]) for r in status_rows},
        "dispatches": [
            {"channel": r["channel"], "status": r["status"], "count": int(r["cnt"])} for r in dispatch_rows
        ],
    }


class TemplateRequest(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    channel: Literal["sms", "whatsapp", "push", "email"]
    language: str = Field(default="en", min_length=2, max_length=10)
    subject: Optional[str] = Field(default=None, max_length=255)
    body_template: str = Field(..., min_length=1)


@router.get("/templates")
async def list_templates(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (await db.execute(select(NotificationTemplate).order_by(NotificationTemplate.event_type))).scalars().all()
    return {
        "items": [
            {
                "id": t.id,
                "event_type": t.event_type,
                "channel": t.channel,
                "language": t.language,
                "subject": t.subject,
                "body_template": t.body_template,
                "is_active": t.is_active,
                "version": t.version,
            }
            for t in rows
        ]
    }


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.event_type == payload.event_type,
            NotificationTemplate.channel == payload.channel,
            NotificationTemplate.language == payload.language,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TEMPLATE_ALREADY_EXISTS")

    tmpl = NotificationTemplate(**payload.model_dump())
    db.add(tmpl)
    await db.flush()
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_notifications", action="template_created",
        target_id=tmpl.id, changes=payload.model_dump(),
    )
    await db.commit()
    return {"id": tmpl.id, "event_type": tmpl.event_type, "channel": tmpl.channel}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: int,
    payload: TemplateRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    tmpl = await db.scalar(select(NotificationTemplate).where(NotificationTemplate.id == template_id))
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TEMPLATE_NOT_FOUND")

    tmpl.subject = payload.subject
    tmpl.body_template = payload.body_template
    tmpl.version += 1

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_notifications", action="template_updated",
        target_id=template_id, changes={"version": tmpl.version},
    )
    await db.commit()
    return {"id": template_id, "version": tmpl.version}


class BroadcastRequest(BaseModel):
    segment: Literal["all_active", "pending_kyc", "specific_users"]
    user_ids: Optional[list[int]] = None
    category: str = Field(default="system")
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    channels: list[Literal["sms", "push", "email", "whatsapp"]] = Field(default_factory=lambda: ["push"])


@router.post("/broadcast", status_code=status.HTTP_201_CREATED)
async def broadcast_notification(
    payload: BroadcastRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    if payload.segment == "specific_users":
        if not payload.user_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="USER_IDS_REQUIRED")
        target_ids = payload.user_ids
    else:
        status_filter = "active" if payload.segment == "all_active" else "pending_kyc"
        rows = await db.execute(
            text("SELECT id FROM users WHERE deleted_at IS NULL AND status = :status"), {"status": status_filter}
        )
        target_ids = [r[0] for r in rows.fetchall()]

    if not target_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NO_MATCHING_USERS")
    if len(target_ids) > 5000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SEGMENT_TOO_LARGE_MAX_5000")

    created_ids = []
    for user_id in target_ids:
        notif = Notification(
            user_id=user_id,
            source_event="admin.broadcast",
            source_reference=f"admin:{current_admin.id}",
            category=payload.category,
            priority=payload.priority,
            title=payload.title,
            body=payload.body,
            status="queued",
            idempotency_key=f"admin_broadcast:{uuid.uuid4()}",
            channels_requested=payload.channels,
            template_vars={},
        )
        db.add(notif)
        await db.flush()
        created_ids.append(notif.id)

        if hasattr(redis, "redis"):
            for channel in payload.channels:
                queue = _CHANNEL_QUEUES.get(channel)
                if queue:
                    await redis.redis.lpush(
                        queue,
                        json.dumps({"notification_id": notif.id, "user_id": user_id, "channel": channel}),
                    )

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_notifications", action="broadcast_sent",
        target_id=None,
        changes={"segment": payload.segment, "recipient_count": len(target_ids), "title": payload.title},
        severity="critical",
    )
    await db.commit()
    return {"recipient_count": len(created_ids), "notification_ids": created_ids[:20], "status": "queued"}
