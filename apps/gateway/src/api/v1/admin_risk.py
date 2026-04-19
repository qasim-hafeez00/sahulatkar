"""Admin Risk & Blacklist Management — GAP-E from the production audit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal, Optional

from sk_shared.models.auth import AdminUser
from sk_shared.models.admin import RiskBlacklist
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/risk", tags=["Admin Risk"])


class BlacklistCreateRequest(BaseModel):
    entry_type: Literal["user", "device", "ip"]
    value: str = Field(..., min_length=1, max_length=255)
    reason: str = Field(..., min_length=3, max_length=500)
    user_id: Optional[int] = None


@router.get("/blacklist")
async def list_blacklist(
    entry_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    query = select(RiskBlacklist).where(RiskBlacklist.deleted_at.is_(None))
    if entry_type:
        query = query.where(RiskBlacklist.entry_type == entry_type)

    rows = (
        await db.execute(
            query.order_by(RiskBlacklist.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    total = int(
        await db.scalar(
            select(func.count(RiskBlacklist.id)).where(
                RiskBlacklist.deleted_at.is_(None),
                RiskBlacklist.entry_type == entry_type if entry_type else True,
            )
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r.id,
                "entry_type": r.entry_type,
                "value": r.value,
                "reason": r.reason,
                "user_id": r.user_id,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.post("/blacklist", status_code=status.HTTP_201_CREATED)
async def add_to_blacklist(
    payload: BlacklistCreateRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.scalar(
        select(RiskBlacklist).where(
            RiskBlacklist.entry_type == payload.entry_type,
            RiskBlacklist.value == payload.value,
            RiskBlacklist.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="BLACKLIST_ENTRY_EXISTS")

    row = RiskBlacklist(
        entry_type=payload.entry_type,
        value=payload.value,
        reason=payload.reason,
        user_id=payload.user_id,
    )
    db.add(row)
    await db.flush()

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="risk_blacklist",
        action="add_entry",
        target_id=row.id,
        changes={
            "entry_type": payload.entry_type,
            "value": payload.value,
            "reason": payload.reason,
        },
    )
    await db.commit()
    return {
        "id": row.id,
        "entry_type": row.entry_type,
        "value": row.value,
        "reason": row.reason,
        "user_id": row.user_id,
        "created_at": row.created_at,
    }


@router.delete("/blacklist/{entry_id}", status_code=status.HTTP_200_OK)
async def remove_from_blacklist(
    entry_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.scalar(
        select(RiskBlacklist).where(RiskBlacklist.id == entry_id, RiskBlacklist.deleted_at.is_(None))
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BLACKLIST_ENTRY_NOT_FOUND")
    from datetime import datetime, timezone

    row.deleted_at = datetime.now(timezone.utc)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="risk_blacklist",
        action="remove_entry",
        target_id=entry_id,
        changes={},
    )
    await db.commit()
    return {"removed_id": entry_id}
