from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser

from src.core.dependencies import get_current_admin, get_db

router = APIRouter(prefix="/admin/payments", tags=["Admin Payments"])


@router.get("")
async def list_admin_payments(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, alias="q"),
    gateway: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default="created_at"),
    sort_dir: str | None = Query(default="desc"),
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """List all payments with filtering and sorting."""
    offset = (page - 1) * limit
    
    where_clauses = ["payment_transactions.deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    
    if q:
        where_clauses.append("payment_transactions.transaction_id ILIKE :q")
        params["q"] = f"%{q}%"
    
    if gateway:
        where_clauses.append("payment_transactions.gateway = :gateway")
        params["gateway"] = gateway
    
    if status:
        where_clauses.append("payment_transactions.status = :status")
        params["status"] = status
    
    where_clause = " AND ".join(where_clauses)
    sort_col = sort_by or "created_at"
    sort_order = "DESC" if sort_dir == "desc" else "ASC"
    
    query = text(
        f"""
        SELECT 
            payment_transactions.id, payment_transactions.transaction_id,
            payment_transactions.order_id, payment_transactions.amount,
            payment_transactions.currency, payment_transactions.status,
            payment_transactions.method, payment_transactions.gateway,
            payment_transactions.created_at, payment_transactions.settled_at
        FROM payment_transactions
        WHERE {where_clause}
        ORDER BY payment_transactions.{sort_col} {sort_order}
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text(
        f"""
        SELECT COUNT(*)
        FROM payment_transactions
        WHERE {where_clause}
        """
    )
    
    try:
        rows = (await db.execute(query, params)).mappings().all()
        total = int((await db.execute(count_query, params)).scalar_one())
    except Exception:
        rows = []
        total = 0
    
    return {
        "payments": [
            {
                "id": row["id"],
                "transaction_id": row["transaction_id"],
                "order_id": row["order_id"],
                "amount": float(row["amount"]),
                "currency": row["currency"] or "PKR",
                "status": row["status"],
                "method": row["method"],
                "gateway": row["gateway"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "settled_at": row["settled_at"].isoformat() if row["settled_at"] else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{payment_id}")
async def get_admin_payment_detail(
    payment_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get detailed payment information."""
    query = text(
        """
        SELECT 
            payment_transactions.id, payment_transactions.transaction_id,
            payment_transactions.order_id, payment_transactions.amount,
            payment_transactions.currency, payment_transactions.status,
            payment_transactions.method, payment_transactions.gateway,
            payment_transactions.created_at, payment_transactions.settled_at,
            payment_transactions.error_code, payment_transactions.error_message
        FROM payment_transactions
        WHERE payment_transactions.id = :payment_id AND payment_transactions.deleted_at IS NULL
        """
    )
    
    try:
        row = (await db.execute(query, {"payment_id": payment_id})).mappings().one_or_none()
    except Exception:
        row = None
    
    if row is None:
        return {"error": "Payment not found"}
    
    return {
        "id": row["id"],
        "transaction_id": row["transaction_id"],
        "order_id": row["order_id"],
        "amount": float(row["amount"]),
        "currency": row["currency"] or "PKR",
        "status": row["status"],
        "method": row["method"],
        "gateway": row["gateway"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "settled_at": row["settled_at"].isoformat() if row["settled_at"] else None,
        "error": {
            "code": row["error_code"],
            "message": row["error_message"],
        } if row["error_code"] else None,
    }
