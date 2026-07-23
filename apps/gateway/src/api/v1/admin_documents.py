"""Admin Document Management — Phase 4 thin module. Admin-side complement to the KYC queue."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/documents", tags=["Admin Documents"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("")
async def list_documents(
    status_filter: Optional[str] = None,
    document_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        where_clauses.append("d.status = :status_filter")
        params["status_filter"] = status_filter
    if document_type:
        where_clauses.append("d.document_type = :document_type")
        params["document_type"] = document_type
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT d.id, d.user_id, d.document_type, d.status, d.mime_type,
                       d.expiry_date, d.created_at, u.phone
                FROM user_documents d
                LEFT JOIN users u ON u.id = d.user_id
                {where_sql}
                ORDER BY d.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    total = int(
        await db.scalar(
            text(f"SELECT COUNT(*) FROM user_documents d {where_sql}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "user_phone": r["phone"],
                "document_type": r["document_type"],
                "status": r["status"],
                "mime_type": r["mime_type"],
                "expiry_date": _iso(r["expiry_date"]),
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/{document_id}")
async def get_document_detail(
    document_id: int,
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT d.*, u.phone
                FROM user_documents d
                LEFT JOIN users u ON u.id = d.user_id
                WHERE d.id = :id
                """
            ),
            {"id": document_id},
        )
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DOCUMENT_NOT_FOUND")

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_phone": row["phone"],
        "document_type": row["document_type"],
        "file_path_s3": row["file_path_s3"],
        "mime_type": row["mime_type"],
        "status": row["status"],
        "verification_notes": row["verification_notes"],
        "expiry_date": _iso(row["expiry_date"]),
        "created_at": _iso(row["created_at"]),
    }


class DocumentDecisionRequest(BaseModel):
    decision: Literal["verified", "rejected"]
    verification_notes: Optional[str] = Field(default=None, max_length=1000)


@router.post("/{document_id}/decision")
async def decide_document(
    document_id: int,
    payload: DocumentDecisionRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id FROM user_documents WHERE id = :id"), {"id": document_id})
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DOCUMENT_NOT_FOUND")

    await db.execute(
        text(
            """
            UPDATE user_documents
            SET status = :status, verification_notes = :notes, updated_at = NOW()
            WHERE id = :id
            """
        ),
        {"status": payload.decision, "notes": payload.verification_notes, "id": document_id},
    )
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_documents", action=f"document_{payload.decision}",
        target_id=document_id, changes={"notes": payload.verification_notes},
    )
    await db.commit()
    return {"id": document_id, "status": payload.decision}


@router.get("/summary/counts")
async def document_summary(
    current_admin: AdminUser = Depends(RequirePermission("manage_kyc_queue")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(text("SELECT status, COUNT(*) AS cnt FROM user_documents GROUP BY status"))
    ).mappings().all()
    return {"by_status": {r["status"]: int(r["cnt"]) for r in rows}}
