from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.models.order import Order
from sk_shared.models.auth import User
from sk_shared.redis_client import RedisClient
from sk_shared.constants import QueueName

from src.core.dependencies import get_current_admin, get_db, get_redis, RequirePermission

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("")
async def list_admin_orders(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, alias="q"),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default="created_at"),
    sort_dir: str | None = Query(default="desc"),
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """List all orders with filtering and sorting."""
    offset = (page - 1) * limit
    
    where_clauses = ["orders.deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    
    if q:
        where_clauses.append("(LOWER(CAST(orders.id AS TEXT)) LIKE LOWER(:q) OR LOWER('ORD-' || CAST(orders.id AS TEXT)) LIKE LOWER(:q) OR LOWER(users.phone) LIKE LOWER(:q))")
        params["q"] = f"%{q}%"
    
    if status:
        where_clauses.append("orders.status = :status")
        params["status"] = status
    
    where_clause = " AND ".join(where_clauses)
    sort_column_map = {
        "id": "id",
        "order_number": "id",
        "status": "status",
        "total_amount": "total_amount",
        "created_at": "created_at",
    }
    sort_col = sort_column_map.get(sort_by, "created_at")
    sort_order = "DESC" if sort_dir == "desc" else "ASC"
    
    query = text(
        f"""
        SELECT 
            orders.id, orders.status, 
            orders.total_amount, orders.down_payment_amount, 
            orders.created_at,
            users.phone as user_phone,
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
                "order_number": f"ORD-{row['id']}",
                "user_phone": row["user_phone"] or "Unknown",
                "product_name": row["product_name"] or "N/A",
                "status": row["status"],
                "total_amount": float(row["total_amount"]),
                "down_payment": float(row["down_payment_amount"] or 0),
                "created_at": _iso(row["created_at"]),
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
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get detailed order information."""
    query = text(
        """
        SELECT 
            orders.id, orders.status, 
            orders.total_amount, orders.down_payment_amount,
            orders.created_at, orders.user_id,
            users.phone as user_phone,
            products.name as product_name, products.sale_price,
            loans.loan_number, loans.principal_amount, loans.profit_amount,
            loans.total_repayable, loans.total_outstanding, loans.installment_count
        FROM orders
        LEFT JOIN users ON orders.user_id = users.id
        LEFT JOIN products ON orders.product_id = products.id
        LEFT JOIN loans ON loans.order_id = orders.id AND loans.deleted_at IS NULL
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
        "order_number": f"ORD-{row['id']}",
        "status": row["status"],
        "user": {
            "id": row["user_id"],
            "phone": row["user_phone"],
        },
        "product": {
            "name": row["product_name"],
            "price": float(row["sale_price"]) if row["sale_price"] else 0,
        },
        "totals": {
            "total_amount": float(row["total_amount"]),
            "down_payment": float(row["down_payment_amount"] or 0),
            "remaining": float(row["total_amount"]) - float(row["down_payment_amount"] or 0),
        },
        "financial_summary": {
            "loan_number": row["loan_number"],
            "principal": float(row["principal_amount"] or 0),
            "profit": float(row["profit_amount"] or 0),
            "total_repayable": float(row["total_repayable"] or 0),
            "outstanding": float(row["total_outstanding"] or 0),
            "installment_count": row["installment_count"],
        },
        "created_at": _iso(row["created_at"]),
    }


# ============================================================================
# TASK-20: Admin Manual Order Status Override
# ============================================================================

from pydantic import BaseModel, Field
from fastapi import HTTPException, status, Request
from datetime import datetime, timezone
from src.core.audit import record_audit_event
import json


class AdminOrderStatusRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(..., min_length=5, max_length=500)


class AdminOrderRefundRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


@router.put("/{order_id}/status")
async def admin_override_order_status(
    order_id: int,
    payload: AdminOrderStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_orders")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin endpoint to manually override order status for HITL resolution"""
    from sk_shared.models.order import OrderStatusHistory
    
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    
    old_status = order.status
    order.status = payload.status
    
    db.add(OrderStatusHistory(
        order_id=order_id,
        from_status=old_status,
        to_status=payload.status,
        reason=f"admin_override:{payload.reason}",
    ))
    
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_orders",
        action="status_override",
        target_id=order_id,
        changes={
            "from_status": old_status,
            "to_status": payload.status,
            "reason": payload.reason,
        },
    )
    
    await db.commit()
    return {"order_id": order_id, "status": payload.status, "previous_status": old_status}


# ============================================================================
# TASK-21: Admin Order Installments View
# ============================================================================

@router.get("/{order_id}/installments")
async def get_order_installments(
    order_id: int,
    current_admin: AdminUser = Depends(RequirePermission("manage_orders")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin endpoint to view all installments for an order's loan"""
    q = text("""
        SELECT i.id, i.installment_number, i.total_amount, i.due_date,
               i.status, i.paid_at, i.days_overdue, i.late_fee_amount,
               l.loan_number, l.id as loan_id
        FROM installments i
        JOIN loans l ON i.loan_id = l.id
        WHERE l.order_id = :order_id AND i.deleted_at IS NULL
        ORDER BY i.installment_number ASC
    """)
    try:
        rows = (await db.execute(q, {"order_id": order_id})).mappings().all()
    except Exception:
        rows = []
    
    return {
        "order_id": order_id,
        "installments": [
            {
                "id": dict(r)["id"],
                "number": dict(r)["installment_number"],
                "amount": float(dict(r)["total_amount"]),
                "due_date": _iso(dict(r)["due_date"]),
                "status": dict(r)["status"],
                "paid_at": _iso(dict(r)["paid_at"]) if dict(r)["paid_at"] else None,
                "days_overdue": dict(r)["days_overdue"],
                "late_fee": float(dict(r)["late_fee_amount"] or 0),
                "loan_number": dict(r)["loan_number"],
            }
            for r in rows
        ],
    }


@router.get("/{order_id}/payments")
async def get_order_payments(
    order_id: int,
    current_admin: AdminUser = Depends(RequirePermission("manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT id, gateway_txn_id, amount, currency, status, gateway,
               transaction_type, created_at, reconciled_at, failure_code, failure_message
        FROM payment_transactions
        WHERE order_id = :order_id AND deleted_at IS NULL
        ORDER BY created_at DESC
        """
    )
    rows = (await db.execute(q, {"order_id": order_id})).mappings().all()
    return {
        "order_id": order_id,
        "items": [
            {
                "id": r["id"],
                "gateway_txn_id": r["gateway_txn_id"],
                "amount": float(r["amount"] or 0),
                "currency": r["currency"],
                "status": r["status"],
                "gateway": r["gateway"],
                "transaction_type": r["transaction_type"],
                "created_at": _iso(r["created_at"]),
                "reconciled_at": _iso(r["reconciled_at"]),
                "failure_code": r["failure_code"],
                "failure_message": r["failure_message"],
            }
            for r in rows
        ],
    }


@router.get("/{order_id}/timeline")
async def get_order_status_timeline(
    order_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT from_status, to_status, reason, created_at
        FROM order_status_history
        WHERE order_id = :order_id
        ORDER BY created_at ASC
        """
    )
    rows = (await db.execute(q, {"order_id": order_id})).mappings().all()
    return {
        "order_id": order_id,
        "items": [
            {
                "from_status": r["from_status"],
                "to_status": r["to_status"],
                "reason": r["reason"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ],
    }


@router.get("/{order_id}/vcn")
async def get_order_vcn(
    order_id: int,
    current_admin: AdminUser = Depends(RequirePermission("manage_orders")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT id, status, masked_number, card_expiry, expires_at, authorized_amount, loaded_amount,
               charged_amount, issued_at, used_at
        FROM virtual_cards
        WHERE order_id = :order_id AND deleted_at IS NULL
        """
    )
    row = (await db.execute(q, {"order_id": order_id})).mappings().one_or_none()
    if not row:
        return {"order_id": order_id, "vcn_status": "not_issued"}
    return {
        "order_id": order_id,
        "vcn_id": row["id"],
        "vcn_status": row["status"],
        "masked_number": row["masked_number"],
        "card_expiry": _iso(row["card_expiry"]),
        "expires_at": _iso(row["expires_at"]),
        "authorized_amount": float(row["authorized_amount"] or 0),
        "loaded_amount": float(row["loaded_amount"] or 0),
        "charged_amount": float(row["charged_amount"] or 0),
        "issued_at": _iso(row["issued_at"]),
        "used_at": _iso(row["used_at"]),
    }


@router.post("/{order_id}/refund")
async def request_order_refund(
    order_id: int,
    payload: AdminOrderRefundRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_payments")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.deleted_at.is_(None)))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    refundable_statuses = {
        "purchase_confirmed",
        "delivery_pending",
        "in_transit",
        "delivered",
        "completed",
    }
    if str(order.status) not in refundable_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"ORDER_NOT_REFUNDABLE (current status: {order.status})",
        )

    if hasattr(redis, "redis"):
        event = {
            "event": "payment.refund_requested",
            "order_id": order.id,
            "user_id": order.user_id,
            "amount": float(order.total_amount or 0),
            "reason": payload.reason,
            "requested_by_admin_id": current_admin.id,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        await redis.redis.lpush(QueueName.PAYMENT_INITIATE, json.dumps(event))

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_orders",
        action="refund_requested",
        target_id=order.id,
        changes={
            "reason": payload.reason,
            "amount": float(order.total_amount or 0),
            "order_status": order.status,
        },
    )
    await db.commit()
    return {"order_id": order.id, "status": "refund_requested", "queued": True}
