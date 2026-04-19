from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.core.audit import record_audit_event
from src.core.dependencies import get_current_admin, get_db, get_redis, RequirePermission

router = APIRouter(prefix="/admin/payments", tags=["Admin Payments"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("")
async def list_admin_payments(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, alias="q"),
    gateway: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default="created_at"),
    sort_dir: str | None = Query(default="desc"),
    current_admin: AdminUser = Depends(RequirePermission("manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """List all payments with filtering and sorting."""
    offset = (page - 1) * limit
    
    where_clauses = ["payment_transactions.deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}
    
    if q:
        where_clauses.append("LOWER(COALESCE(payment_transactions.gateway_txn_id, '')) LIKE LOWER(:q)")
        params["q"] = f"%{q}%"
    
    if gateway:
        where_clauses.append("payment_transactions.gateway = :gateway")
        params["gateway"] = gateway
    
    if status:
        where_clauses.append("payment_transactions.status = :status")
        params["status"] = status
    
    where_clause = " AND ".join(where_clauses)
    sort_column_map = {
        "id": "id",
        "transaction_id": "gateway_txn_id",
        "amount": "amount",
        "status": "status",
        "created_at": "created_at",
        "settled_at": "reconciled_at",
    }
    sort_col = sort_column_map.get(sort_by, "created_at")
    sort_order = "DESC" if sort_dir == "desc" else "ASC"
    
    query = text(
        f"""
        SELECT 
            payment_transactions.id, payment_transactions.gateway_txn_id,
            payment_transactions.order_id, payment_transactions.amount,
            payment_transactions.currency, payment_transactions.status,
            payment_transactions.gateway,
            payment_transactions.created_at, payment_transactions.reconciled_at
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
                "transaction_id": row["gateway_txn_id"],
                "order_id": row["order_id"],
                "amount": float(row["amount"]),
                "currency": row["currency"] or "PKR",
                "status": row["status"],
                "gateway": row["gateway"],
                "created_at": _iso(row["created_at"]),
                "settled_at": _iso(row["reconciled_at"]),
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
    current_admin: AdminUser = Depends(RequirePermission("manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get detailed payment information."""
    query = text(
        """
        SELECT 
            payment_transactions.id, payment_transactions.gateway_txn_id,
            payment_transactions.order_id, payment_transactions.amount,
            payment_transactions.currency, payment_transactions.status,
            payment_transactions.gateway,
            payment_transactions.created_at, payment_transactions.reconciled_at,
            payment_transactions.failure_code, payment_transactions.failure_message
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
        "transaction_id": row["gateway_txn_id"],
        "order_id": row["order_id"],
        "amount": float(row["amount"]),
        "currency": row["currency"] or "PKR",
        "status": row["status"],
        "gateway": row["gateway"],
        "created_at": _iso(row["created_at"]),
        "settled_at": _iso(row["reconciled_at"]),
        "error": {
            "code": row["failure_code"],
            "message": row["failure_message"],
        } if row["failure_code"] else None,
    }


class ManualPayRequest(BaseModel):
    reason: str = Field(..., min_length=5)
    reference: str | None = None


@router.post("/installment/{installment_id}/manual-pay")
async def manual_pay_installment(
    installment_id: int,
    payload: ManualPayRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_payments")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    from sk_shared.models.payment import Installment, Loan, PaymentTransaction
    from datetime import datetime, timezone
    import json

    stmt = select(Installment).where(Installment.id == installment_id, Installment.deleted_at.is_(None))
    installment = await db.scalar(stmt)
    if not installment:
        raise HTTPException(status_code=404, detail="INSTALLMENT_NOT_FOUND")
    if installment.status == "paid":
        raise HTTPException(status_code=409, detail="ALREADY_PAID")

    loan = await db.scalar(select(Loan).where(Loan.id == installment.loan_id))
    
    # Create a manual payment transaction record
    txn = PaymentTransaction(
        user_id=installment.user_id,
        order_id=loan.order_id if loan else None,
        loan_id=loan.id if loan else None,
        installment_id=installment.id,
        amount=float(installment.total_amount),
        gateway="manual",
        gateway_txn_id=payload.reference or f"MAN-{installment_id}-{int(datetime.now().timestamp())}",
        status="confirmed",
        reconciled_at=datetime.now(timezone.utc)
    )
    db.add(txn)
    
    # Update installment
    installment.status = "paid"
    installment.paid_at = datetime.now(timezone.utc)
    
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_payments",
        action="manual_payment_confirmed",
        target_id=installment_id,
        changes={"reason": payload.reason, "reference": payload.reference, "amount": float(installment.total_amount)},
    )
    
    await db.commit()
    
    # Enqueue for ledger sync (GAP-32 implied)
    if hasattr(redis, "redis"):
        from sk_shared.constants import QueueName
        event = json.dumps({
            "event": "payment.manual_confirmed",
            "installment_id": installment_id,
            "admin_id": current_admin.id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        await redis.redis.lpush(QueueName.PAYMENT_WEBHOOK, event)

    return {"status": "ok", "installment_id": installment_id, "transaction_id": txn.gateway_txn_id}
