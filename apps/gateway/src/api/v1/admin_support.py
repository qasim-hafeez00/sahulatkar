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
    where_clauses = ["1=1"]
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
        SELECT id, ticket_number, user_id, subject, category, priority, status,
               assigned_to, sla_deadline, resolved_at, closed_at,
               satisfaction_score, satisfaction_comment, created_at, updated_at
        FROM support_tickets
        WHERE id = :ticket_id
        """
    )
    try:
        row = (await db.execute(q, {"ticket_id": ticket_id})).mappings().one_or_none()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    messages = (
        await db.execute(
            text(
                """
                SELECT id, sender_type, sender_id, message_text, is_internal_note, created_at
                FROM ticket_messages
                WHERE ticket_id = :ticket_id
                ORDER BY created_at ASC
                """
            ),
            {"ticket_id": ticket_id},
        )
    ).mappings().all()

    return {
        "id": row["id"],
        "ticket_number": row["ticket_number"],
        "user_id": row["user_id"],
        "subject": row["subject"],
        "category": row["category"],
        "priority": row["priority"],
        "status": row["status"],
        "assigned_to": row["assigned_to"],
        "sla_deadline": _iso(row["sla_deadline"]),
        "resolved_at": _iso(row["resolved_at"]),
        "closed_at": _iso(row["closed_at"]),
        "satisfaction_score": row["satisfaction_score"],
        "satisfaction_comment": row["satisfaction_comment"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "messages": [
            {
                "id": m["id"],
                "sender_type": m["sender_type"],
                "sender_id": m["sender_id"],
                "message_text": m["message_text"],
                "is_internal_note": m["is_internal_note"],
                "created_at": _iso(m["created_at"]),
            }
            for m in messages
        ],
    }


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: int,
    payload: TicketAssignRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await db.execute(
            text(
                "UPDATE support_tickets SET assigned_to = :admin_id, status = 'in_progress', updated_at = :now WHERE id = :ticket_id"
            ),
            {"admin_id": payload.admin_id, "now": now, "ticket_id": ticket_id},
        )
        row = (
            await db.execute(
                text("SELECT id, status FROM support_tickets WHERE id = :ticket_id"),
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
    current_admin: AdminUser = Depends(RequirePermission("manage_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await db.execute(
            text(
                "UPDATE support_tickets SET status = 'resolved', resolved_at = :now, updated_at = :now WHERE id = :ticket_id"
            ),
            {"now": now, "ticket_id": ticket_id},
        )
        # No dedicated resolution_note column on support_tickets — recorded as an
        # agent message in ticket_messages, the same table the ticket thread uses.
        await db.execute(
            text(
                """
                INSERT INTO ticket_messages (ticket_id, sender_type, sender_id, message_text, is_internal_note)
                VALUES (:ticket_id, 'agent', :admin_id, :note, false)
                """
            ),
            {"ticket_id": ticket_id, "admin_id": current_admin.id, "note": payload.resolution_note},
        )
        row = (
            await db.execute(
                text("SELECT id, status FROM support_tickets WHERE id = :ticket_id"),
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
    current_admin: AdminUser = Depends(RequirePermission("manage_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await db.execute(
            text("UPDATE support_tickets SET status = 'closed', closed_at = :now, updated_at = :now WHERE id = :ticket_id"),
            {"now": now, "ticket_id": ticket_id},
        )
        row = (
            await db.execute(
                text("SELECT id, status FROM support_tickets WHERE id = :ticket_id"),
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


# ============================================================================
# Module 7 — dashboard KPIs, canned responses, CSAT
# ============================================================================


@router.get("/dashboard")
async def support_dashboard(
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status_rows = (
        await db.execute(
            text("SELECT status, COUNT(*) AS cnt FROM support_tickets GROUP BY status")
        )
    ).mappings().all()
    category_rows = (
        await db.execute(
            text("SELECT category, COUNT(*) AS cnt FROM support_tickets GROUP BY category")
        )
    ).mappings().all()
    sla_breached = await db.scalar(
        text(
            """
            SELECT COUNT(*) FROM support_tickets
            WHERE status NOT IN ('resolved', 'closed')
              AND sla_deadline IS NOT NULL AND sla_deadline < NOW()
            """
        )
    )
    avg_resolution_hours = await db.scalar(
        text(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0)
            FROM support_tickets
            WHERE resolved_at IS NOT NULL
              AND created_at >= NOW() - INTERVAL '30 days'
            """
        )
    )

    return {
        "by_status": {r["status"]: int(r["cnt"]) for r in status_rows},
        "by_category": {r["category"]: int(r["cnt"]) for r in category_rows},
        "sla_breached": int(sla_breached or 0),
        "avg_resolution_hours_30d": round(float(avg_resolution_hours), 1) if avg_resolution_hours else None,
    }


@router.get("/csat")
async def csat_summary(
    days: int = 90,
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS response_count,
                    COALESCE(AVG(satisfaction_score), 0) AS avg_score,
                    COUNT(*) FILTER (WHERE satisfaction_score >= 4) AS satisfied_count
                FROM support_tickets
                WHERE satisfaction_score IS NOT NULL
                  AND created_at >= NOW() - make_interval(days => :days)
                """
            ),
            {"days": days},
        )
    ).mappings().one()
    distribution_rows = (
        await db.execute(
            text(
                """
                SELECT satisfaction_score, COUNT(*) AS cnt
                FROM support_tickets
                WHERE satisfaction_score IS NOT NULL
                  AND created_at >= NOW() - make_interval(days => :days)
                GROUP BY satisfaction_score
                ORDER BY satisfaction_score
                """
            ),
            {"days": days},
        )
    ).mappings().all()

    response_count = int(row["response_count"] or 0)
    satisfied_count = int(row["satisfied_count"] or 0)
    return {
        "response_count": response_count,
        "avg_score": round(float(row["avg_score"] or 0), 2),
        "csat_pct": round((satisfied_count / response_count * 100), 1) if response_count > 0 else None,
        "distribution": {int(r["satisfaction_score"]): int(r["cnt"]) for r in distribution_rows},
    }


class CannedResponseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    category: Optional[str] = Field(default=None, max_length=50)
    language: str = Field(default="en", min_length=2, max_length=2)


@router.get("/canned-responses")
async def list_canned_responses(
    category: Optional[str] = None,
    active_only: bool = True,
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where_clauses = []
    params: dict = {}
    if active_only:
        where_clauses.append("is_active = true")
    if category:
        where_clauses.append("category = :category")
        params["category"] = category
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, title, body, category, language, tags, usage_count, last_used_at, is_active, created_at
                FROM canned_responses
                {where_sql}
                ORDER BY usage_count DESC, title ASC
                """
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": r["id"],
                "title": r["title"],
                "body": r["body"],
                "category": r["category"],
                "language": r["language"],
                "tags": r["tags"] or [],
                "usage_count": r["usage_count"],
                "last_used_at": _iso(r["last_used_at"]),
                "is_active": r["is_active"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.post("/canned-responses", status_code=status.HTTP_201_CREATED)
async def create_canned_response(
    payload: CannedResponseRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                INSERT INTO canned_responses (title, body, category, language, created_by)
                VALUES (:title, :body, :category, :language, :created_by)
                RETURNING id, created_at
                """
            ),
            {
                "title": payload.title,
                "body": payload.body,
                "category": payload.category,
                "language": payload.language,
                "created_by": current_admin.id,
            },
        )
    ).mappings().one()

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_support", action="create_canned_response",
        target_id=row["id"], changes={"title": payload.title},
    )
    await db.commit()
    return {"id": row["id"], "title": payload.title, "created_at": _iso(row["created_at"])}


@router.put("/canned-responses/{response_id}")
async def update_canned_response(
    response_id: int,
    payload: CannedResponseRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id FROM canned_responses WHERE id = :id"), {"id": response_id})
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CANNED_RESPONSE_NOT_FOUND")

    await db.execute(
        text(
            """
            UPDATE canned_responses
            SET title = :title, body = :body, category = :category, language = :language, updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "title": payload.title,
            "body": payload.body,
            "category": payload.category,
            "language": payload.language,
            "id": response_id,
        },
    )

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_support", action="update_canned_response",
        target_id=response_id, changes={"title": payload.title},
    )
    await db.commit()
    return {"id": response_id, "status": "updated"}


@router.delete("/canned-responses/{response_id}")
async def deactivate_canned_response(
    response_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id FROM canned_responses WHERE id = :id"), {"id": response_id})
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CANNED_RESPONSE_NOT_FOUND")

    await db.execute(
        text("UPDATE canned_responses SET is_active = false, updated_at = NOW() WHERE id = :id"),
        {"id": response_id},
    )

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_support", action="deactivate_canned_response",
        target_id=response_id, changes={},
    )
    await db.commit()
    return {"id": response_id, "status": "deactivated"}
