from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin", tags=["Admin Installments"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("/installments")
async def list_admin_installments(
    status: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    loan_id: int | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit

    where = ["i.deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if status:
        where.append("i.status = :status")
        params["status"] = status
    if user_id is not None:
        where.append("i.user_id = :user_id")
        params["user_id"] = user_id
    if loan_id is not None:
        where.append("i.loan_id = :loan_id")
        params["loan_id"] = loan_id
    if overdue_only:
        where.append("i.status = 'overdue'")

    where_clause = " AND ".join(where)

    q = text(
        f"""
        SELECT
            i.id, i.loan_id, i.user_id, i.installment_number, i.total_amount,
            i.due_date, i.status, i.paid_at, i.days_overdue, i.late_fee_amount,
            l.order_id, l.loan_number
        FROM installments i
        LEFT JOIN loans l ON l.id = i.loan_id
        WHERE {where_clause}
        ORDER BY i.due_date ASC, i.installment_number ASC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text(
        f"""
        SELECT COUNT(*)
        FROM installments i
        WHERE {where_clause}
        """
    )

    try:
        rows = (await db.execute(q, params)).mappings().all()
        total = int((await db.execute(count_q, params)).scalar_one() or 0)
    except Exception:
        rows, total = [], 0

    return {
        "items": [
            {
                "id": r["id"],
                "loan_id": r["loan_id"],
                "loan_number": r["loan_number"],
                "order_id": r["order_id"],
                "user_id": r["user_id"],
                "installment_number": r["installment_number"],
                "amount": float(r["total_amount"] or 0),
                "due_date": _iso(r["due_date"]),
                "status": r["status"],
                "paid_at": _iso(r["paid_at"]),
                "days_overdue": r["days_overdue"],
                "late_fee_amount": float(r["late_fee_amount"] or 0),
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }
