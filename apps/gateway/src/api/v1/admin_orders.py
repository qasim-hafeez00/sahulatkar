from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.models.order import Order
from sk_shared.redis_client import RedisClient
from sk_shared.constants import OrderState, QueueName

# P1-07: the set of legal order states, derived from OrderState so it can
# never drift out of sync with the canonical list.
_VALID_ORDER_STATES = frozenset(
    v for k, v in vars(OrderState).items() if not k.startswith("_") and isinstance(v, str)
)

from src.core.audit import record_audit_event
from src.core.dependencies import get_db, get_redis, RequirePermission

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
            orders.id, orders.order_number, orders.status,
            orders.total_amount, orders.down_payment_amount,
            orders.created_at,
            users.phone as user_phone,
            COALESCE(products.name, orders.product_snapshot->>'name') as product_name
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
                "order_number": row["order_number"] or f"ORD-{row['id']}",
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


@router.get("/summary")
async def orders_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    status_rows = (
        await db.execute(
            text("SELECT status, COUNT(*) AS cnt FROM orders WHERE deleted_at IS NULL GROUP BY status")
        )
    ).mappings().all()
    totals = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_orders,
                    COUNT(*) FILTER (WHERE status NOT IN ('cancelled', 'refunded')) AS active_orders,
                    COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS orders_today,
                    COALESCE(AVG(total_amount) FILTER (WHERE status NOT IN ('cancelled', 'refunded')), 0) AS avg_order_value,
                    COALESCE(SUM(total_amount) FILTER (WHERE status NOT IN ('cancelled', 'refunded')), 0) AS gmv
                FROM orders
                WHERE deleted_at IS NULL
                """
            )
        )
    ).mappings().one()

    return {
        "by_status": {r["status"]: int(r["cnt"]) for r in status_rows},
        "total_orders": int(totals["total_orders"]),
        "active_orders": int(totals["active_orders"]),
        "orders_today": int(totals["orders_today"]),
        "avg_order_value": float(totals["avg_order_value"] or 0),
        "gmv": float(totals["gmv"] or 0),
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
            orders.id, orders.order_number, orders.status,
            orders.total_amount, orders.down_payment_amount,
            orders.created_at, orders.user_id,
            users.phone as user_phone,
            COALESCE(products.name, orders.product_snapshot->>'name') as product_name,
            products.sale_price,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    return {
        "id": row["id"],
        "order_number": row["order_number"] or f"ORD-{row['id']}",
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

class AdminOrderStatusRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    reason: str = Field(..., min_length=5, max_length=500)

    @field_validator("status")
    @classmethod
    def status_must_be_known_order_state(cls, v: str) -> str:
        # P1-07: previously any string was accepted and written straight to
        # Order.status — a typo or compromised admin token could park an
        # order in a state no other code recognizes, with no way to recover
        # via the normal flow (only another manual override).
        if v not in _VALID_ORDER_STATES:
            raise ValueError(
                f"Unknown order status '{v}'. Must be one of: {sorted(_VALID_ORDER_STATES)}"
            )
        return v


class AdminOrderRefundRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class AdminOrderRestructureRequest(BaseModel):
    new_installment_count: int = Field(..., gt=0, le=12)
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
        severity="critical",
    )
    await db.commit()
    return {"order_id": order.id, "status": "refund_requested", "queued": True}


@router.post("/{order_id}/restructure")
async def restructure_order_loan(
    order_id: int,
    payload: AdminOrderRestructureRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_orders")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    from sk_shared.models.payment import Loan
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.deleted_at.is_(None)))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    loan = await db.scalar(select(Loan).where(Loan.order_id == order_id, Loan.deleted_at.is_(None)))
    if loan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LOAN_NOT_FOUND")

    if hasattr(redis, "redis"):
        event = {
            "event": "loan.restructure_requested",
            "order_id": order.id,
            "loan_id": loan.id,
            "new_installment_count": payload.new_installment_count,
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
        action="loan_restructure_requested",
        target_id=order.id,
        changes={
            "old_installment_count": loan.installment_count,
            "new_installment_count": payload.new_installment_count,
            "reason": payload.reason,
        },
        severity="critical",
    )
    await db.commit()
    return {"order_id": order.id, "status": "restructure_requested", "queued": True}


# ============================================================================
# Module 3 — manual order creation, communications log
# ============================================================================


class CreateManualOrderRequest(BaseModel):
    user_id: int
    product_name: str = Field(..., min_length=1, max_length=255)
    total_amount: float = Field(..., gt=0)
    down_payment_pct: float | None = Field(default=None, ge=0, le=100)
    merchant_id: int | None = None
    input_url: str | None = Field(default=None, max_length=2048)
    notes: str = Field(..., min_length=3, max_length=1000)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_manual_order(
    payload: CreateManualOrderRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_orders")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_exists = await db.scalar(text("SELECT 1 FROM users WHERE id = :uid AND deleted_at IS NULL"), {"uid": payload.user_id})
    if not user_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    down_payment_pct = payload.down_payment_pct
    if down_payment_pct is None:
        default_pct = await db.scalar(text("SELECT param_value FROM system_parameters WHERE param_key = 'down_payment_pct'"))
        down_payment_pct = float(default_pct) if default_pct else 25.0
    down_payment_amount = round(payload.total_amount * down_payment_pct / 100, 2)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO orders (
                    user_id, merchant_id, input_url, status, product_snapshot,
                    total_amount, currency, down_payment_amount, down_payment_pct,
                    product_description, admin_notes
                ) VALUES (
                    :user_id, :merchant_id, :input_url, 'contracts_pending', :product_snapshot,
                    :total_amount, 'PKR', :down_payment_amount, :down_payment_pct,
                    :product_description, :admin_notes
                )
                RETURNING id, order_number, created_at
                """
            ),
            {
                "user_id": payload.user_id,
                "merchant_id": payload.merchant_id,
                "input_url": payload.input_url,
                "product_snapshot": json.dumps({"name": payload.product_name, "manual_entry": True}),
                "total_amount": payload.total_amount,
                "down_payment_amount": down_payment_amount,
                "down_payment_pct": down_payment_pct,
                "product_description": payload.product_name,
                "admin_notes": f"Manually created by admin #{current_admin.id}: {payload.notes}",
            },
        )
    ).mappings().one()

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_orders",
        action="manual_order_created",
        target_id=row["id"],
        changes={"user_id": payload.user_id, "total_amount": payload.total_amount, "notes": payload.notes},
    )
    await db.commit()
    return {
        "id": row["id"],
        "order_number": row["order_number"],
        "status": "contracts_pending",
        "down_payment_amount": down_payment_amount,
        "created_at": _iso(row["created_at"]),
    }


@router.get("/{order_id}/communications")
async def get_order_communications(
    order_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order_exists = await db.scalar(text("SELECT 1 FROM orders WHERE id = :id AND deleted_at IS NULL"), {"id": order_id})
    if not order_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    rows = (
        await db.execute(
            text(
                """
                SELECT id, source_event, category, priority, title, body, status,
                       is_read, created_at
                FROM notifications
                WHERE source_reference = :ref
                ORDER BY created_at DESC
                """
            ),
            {"ref": f"order:{order_id}"},
        )
    ).mappings().all()

    return {
        "order_id": order_id,
        "items": [
            {
                "id": r["id"],
                "source_event": r["source_event"],
                "category": r["category"],
                "priority": r["priority"],
                "title": r["title"],
                "body": r["body"],
                "status": r["status"],
                "is_read": r["is_read"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ],
    }
