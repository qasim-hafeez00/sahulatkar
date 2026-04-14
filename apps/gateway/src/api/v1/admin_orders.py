from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.models.order import Order
from sk_shared.models.auth import User

from src.core.dependencies import get_current_admin, get_db

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


@router.get("")
async def list_admin_orders(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, alias="q"),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default="created_at"),
    sort_dir: str | None = Query(default="desc"),
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """List all orders with filtering and sorting."""
    offset = (page - 1) * limit
    
    where_clauses = ["orders.deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    
    if q:
        where_clauses.append("(orders.order_number ILIKE :q OR users.email ILIKE :q)")
        params["q"] = f"%{q}%"
    
    if status:
        where_clauses.append("orders.status = :status")
        params["status"] = status
    
    where_clause = " AND ".join(where_clauses)
    sort_col = sort_by or "created_at"
    sort_order = "DESC" if sort_dir == "desc" else "ASC"
    
    query = text(
        f"""
        SELECT 
            orders.id, orders.order_number, orders.status, 
            orders.total_amount, orders.down_payment_amount, 
            orders.created_at,
            users.email as user_email,
            products.name as product_name
        FROM orders
        LEFT JOIN users ON orders.user_id = users.id
        LEFT JOIN products ON orders.product_id = products.id
        WHERE {where_clause}
        ORDER BY orders.{sort_col} {sort_order}
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text(
        f"""
        SELECT COUNT(*)
        FROM orders
        LEFT JOIN users ON orders.user_id = users.id
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
        "orders": [
            {
                "id": row["id"],
                "order_number": row["order_number"],
                "user_email": row["user_email"] or "Unknown",
                "product_name": row["product_name"] or "N/A",
                "status": row["status"],
                "total_amount": float(row["total_amount"]),
                "down_payment": float(row["down_payment_amount"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{order_id}")
async def get_admin_order_detail(
    order_id: int,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get detailed order information."""
    query = text(
        """
        SELECT 
            orders.id, orders.order_number, orders.status, 
            orders.total_amount, orders.down_payment_amount,
            orders.created_at, orders.user_id,
            users.email as user_email, users.phone as user_phone,
            products.name as product_name, products.sale_price
        FROM orders
        LEFT JOIN users ON orders.user_id = users.id
        LEFT JOIN products ON orders.product_id = products.id
        WHERE orders.id = :order_id AND orders.deleted_at IS NULL
        """
    )
    
    try:
        row = (await db.execute(query, {"order_id": order_id})).mappings().one_or_none()
    except Exception:
        row = None
    
    if row is None:
        return {"error": "Order not found"}
    
    return {
        "id": row["id"],
        "order_number": row["order_number"],
        "status": row["status"],
        "user": {
            "id": row["user_id"],
            "email": row["user_email"],
            "phone": row["user_phone"],
        },
        "product": {
            "name": row["product_name"],
            "price": float(row["sale_price"]) if row["sale_price"] else 0,
        },
        "totals": {
            "total_amount": float(row["total_amount"]),
            "down_payment": float(row["down_payment_amount"]),
            "remaining": float(row["total_amount"]) - float(row["down_payment_amount"]),
        },
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
