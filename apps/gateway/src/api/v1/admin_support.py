from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_current_admin, get_db

router = APIRouter(prefix="/admin/support", tags=["Admin Support"])


class TicketAssignRequest(BaseModel):
    admin_id: int


class TicketResolveRequest(BaseModel):
    resolution_note: str = Field(..., min_length=5, max_length=1000)


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("/tickets")
async def list_support_tickets(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = ["deleted_at IS NULL"]
    params: dict = {"limit": limit, "offset": offset}

    if status:
        where_clauses.append("status = :status")
        params["status"] = status

    where_sql = " AND ".join(where_clauses)
    q = text(
        f"""
        SELECT id, user_id, subject, status, assigned_to, created_at, updated_at
        FROM support_tickets
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text(f"SELECT COUNT(*) FROM support_tickets WHERE {where_sql}")

    try:
        rows = (await db.execute(q, params)).mappings().all()
        total = int((await db.execute(count_q, params)).scalar_one() or 0)
    except Exception:
        rows, total = [], 0

    return {
        "items": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "subject": r["subject"],
                "status": r["status"],
                "assigned_to": r["assigned_to"],
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/tickets/{ticket_id}")
async def get_ticket_detail(
    ticket_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT id, user_id, subject, description, status, assigned_to,
               resolution_note, created_at, updated_at
        FROM support_tickets
        WHERE id = :ticket_id AND deleted_at IS NULL
        """
    )
    try:
        row = (await db.execute(q, {"ticket_id": ticket_id})).mappings().one_or_none()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "subject": row["subject"],
        "description": row["description"],
        "status": row["status"],
        "assigned_to": row["assigned_to"],
        "resolution_note": row["resolution_note"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: int,
    payload: TicketAssignRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await db.execute(
            text(
                "UPDATE support_tickets SET assigned_to = :admin_id, status = 'in_progress', updated_at = :now WHERE id = :ticket_id AND deleted_at IS NULL"
            ),
            {"admin_id": payload.admin_id, "now": datetime.now(timezone.utc), "ticket_id": ticket_id},
        )
        row = (
            await db.execute(
                text("SELECT id, status FROM support_tickets WHERE id = :ticket_id AND deleted_at IS NULL"),
                {"ticket_id": ticket_id},
            )
        ).mappings().one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"SUPPORT_TABLE_UNAVAILABLE: {exc}")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_support", action="assign_ticket",
        target_id=ticket_id, changes={"assigned_to": payload.admin_id},
    )
    await db.commit()
    return {"ticket_id": row["id"], "status": row["status"], "assigned_to": payload.admin_id}


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: int,
    payload: TicketResolveRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await db.execute(
            text(
                "UPDATE support_tickets SET status = 'resolved', resolution_note = :note, updated_at = :now WHERE id = :ticket_id AND deleted_at IS NULL"
            ),
            {"note": payload.resolution_note, "now": datetime.now(timezone.utc), "ticket_id": ticket_id},
        )
        row = (
            await db.execute(
                text("SELECT id, status FROM support_tickets WHERE id = :ticket_id AND deleted_at IS NULL"),
                {"ticket_id": ticket_id},
            )
        ).mappings().one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"SUPPORT_TABLE_UNAVAILABLE: {exc}")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_support", action="resolve_ticket",
        target_id=ticket_id, changes={"resolution_note": payload.resolution_note},
    )
    await db.commit()
    return {"ticket_id": row["id"], "status": row["status"]}


@router.post("/tickets/{ticket_id}/close")
async def close_ticket(
    ticket_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await db.execute(
            text("UPDATE support_tickets SET status = 'closed', updated_at = :now WHERE id = :ticket_id AND deleted_at IS NULL"),
            {"now": datetime.now(timezone.utc), "ticket_id": ticket_id},
        )
        row = (
            await db.execute(
                text("SELECT id, status FROM support_tickets WHERE id = :ticket_id AND deleted_at IS NULL"),
                {"ticket_id": ticket_id},
            )
        ).mappings().one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"SUPPORT_TABLE_UNAVAILABLE: {exc}")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_support", action="close_ticket",
        target_id=ticket_id, changes={},
    )
    await db.commit()
    return {"ticket_id": row["id"], "status": row["status"]}
