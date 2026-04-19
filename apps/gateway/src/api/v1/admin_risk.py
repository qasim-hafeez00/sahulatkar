"""Admin Risk & Blacklist Management — GAP-E from the production audit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal, Optional

from sk_shared.models.auth import AdminUser
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
    where = "WHERE deleted_at IS NULL"
    params: dict = {"limit": limit, "offset": offset}
    if entry_type:
        where += " AND entry_type = :entry_type"
        params["entry_type"] = entry_type

    q = text(
        f"""
        SELECT id, entry_type, value, reason, user_id, created_at
        FROM risk_blacklist
        {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text(f"SELECT COUNT(*) FROM risk_blacklist {where}")
    try:
        rows = (await db.execute(q, params)).mappings().all()
        total = int((await db.execute(count_q, params)).scalar_one())
    except Exception:
        rows, total = [], 0

    return {
        "items": [
            {
                "id": r["id"],
                "entry_type": r["entry_type"],
                "value": r["value"],
                "reason": r["reason"],
                "user_id": r["user_id"],
                "created_at": r["created_at"],
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
    q = text(
        """
        INSERT INTO risk_blacklist (entry_type, value, reason, user_id)
        VALUES (:entry_type, :value, :reason, :user_id)
        RETURNING id, entry_type, value, reason, user_id, created_at
        """
    )
    try:
        row = (
            await db.execute(
                q,
                {
                    "entry_type": payload.entry_type,
                    "value": payload.value,
                    "reason": payload.reason,
                    "user_id": payload.user_id,
                },
            )
        ).mappings().one()
        await db.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"BLACKLIST_INSERT_FAILED: {exc}",
        )

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="risk_blacklist",
        action="add_entry",
        target_id=row["id"],
        changes={
            "entry_type": payload.entry_type,
            "value": payload.value,
            "reason": payload.reason,
        },
    )
    await db.commit()
    return dict(row)


@router.delete("/blacklist/{entry_id}", status_code=status.HTTP_200_OK)
async def remove_from_blacklist(
    entry_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        UPDATE risk_blacklist
        SET deleted_at = CURRENT_TIMESTAMP
        WHERE id = :entry_id AND deleted_at IS NULL
        RETURNING id
        """
    )
    try:
        row = (await db.execute(q, {"entry_id": entry_id})).mappings().one_or_none()
        await db.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"BLACKLIST_DELETE_FAILED: {exc}",
        )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BLACKLIST_ENTRY_NOT_FOUND")

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
