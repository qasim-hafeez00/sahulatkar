from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser

from src.core.dependencies import get_current_admin, get_db, RequirePermission
from src.core.audit import record_audit_event

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


class UpdateUserStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|suspended|blocked)$")


class UpdateCreditLimitRequest(BaseModel):
    new_limit: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=255)


@router.get("")
async def list_admin_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default="created_at"),
    sort_dir: str | None = Query(default="desc"),
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = (page - 1) * limit
    where_clauses = ["deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if search:
        where_clauses.append("phone ILIKE :search")
        params["search"] = f"%{search}%"
    if status:
        where_clauses.append("status = :status")
        params["status"] = status

    sort_column_map = {
        "id": "id",
        "phone": "phone",
        "status": "status",
        "created_at": "created_at",
        "failed_login_attempts": "failed_login_attempts",
        "locked_until": "locked_until",
    }
    sort_column = sort_column_map.get(sort_by or "created_at", "created_at")
    sort_order = "ASC" if (sort_dir or "desc").lower() == "asc" else "DESC"

    query = text(
        """
        SELECT id, phone, status, created_at, failed_login_attempts, locked_until
        FROM users
        WHERE {where_clause}
        ORDER BY {sort_column} {sort_order}
        LIMIT :limit OFFSET :offset
        """.format(where_clause=" AND ".join(where_clauses), sort_column=sort_column, sort_order=sort_order)
    )

    count_query = text(
        "SELECT COUNT(*) FROM users WHERE {where_clause}".format(where_clause=" AND ".join(where_clauses))
    )

    try:
        rows = (await db.execute(query, params)).mappings().all()
        total = int((await db.execute(count_query, params)).scalar_one())
    except Exception:
        rows = []
        total = 0

    return {
        "requested_by": {
            "admin_id": current_admin.id,
            "email": current_admin.email,
        },
        "items": [
            {
                "id": row["id"],
                "phone": row["phone"],
                "status": row["status"],
                "created_at": row["created_at"],
                "failed_login_attempts": row["failed_login_attempts"],
                "locked_until": row["locked_until"],
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
        },
    }


@router.get("/{user_id}")
async def get_admin_user_detail(
    user_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    query = text(
        """
        SELECT id, phone, status, created_at, failed_login_attempts, locked_until
        FROM users
        WHERE id = :user_id AND deleted_at IS NULL
        """
    )

    try:
        row = (await db.execute(query, {"user_id": user_id})).mappings().one_or_none()
    except Exception:
        row = None

    if row is None:
        return {
            "requested_by": {
                "admin_id": current_admin.id,
                "email": current_admin.email,
            },
            "user": None,
        }

    return {
        "requested_by": {
            "admin_id": current_admin.id,
            "email": current_admin.email,
        },
        "user": {
            "id": row["id"],
            "phone": row["phone"],
            "status": row["status"],
            "created_at": row["created_at"],
            "failed_login_attempts": row["failed_login_attempts"],
            "locked_until": row["locked_until"],
        },
        "tabs": ["personal", "financial", "orders", "payments", "activity"],
    }


@router.put("/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("update_user")),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            text("UPDATE users SET status = :status WHERE id = :user_id AND deleted_at IS NULL RETURNING id, status"),
            {"status": payload.status, "user_id": user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="update_status",
        target_id=user_id,
        changes={"status": payload.status},
    )
    return {"user_id": row["id"], "status": row["status"]}


@router.put("/{user_id}/credit-limit")
async def update_user_credit_limit(
    user_id: int,
    payload: UpdateCreditLimitRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("update_user")),
    db: AsyncSession = Depends(get_db),
):
    # Compatible with environments where credit columns may not exist yet.
    try:
        row = (
            await db.execute(
                text(
                    """
                    UPDATE users
                    SET credit_limit = :new_limit, available_credit = :new_limit
                    WHERE id = :user_id AND deleted_at IS NULL
                    RETURNING id
                    """
                ),
                {"new_limit": payload.new_limit, "user_id": user_id},
            )
        ).mappings().one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"CREDIT_LIMIT_COLUMNS_MISSING: {exc}")

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="credit_limit_override",
        target_id=user_id,
        changes={"new_limit": payload.new_limit, "reason": payload.reason},
    )
    return {"user_id": row["id"], "new_limit": payload.new_limit}


@router.get("/{user_id}/orders")
async def get_user_orders(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = (page - 1) * limit
    q = text(
        """
        SELECT id, status, total_amount, down_payment_amount, created_at, product_description
        FROM orders
        WHERE user_id = :user_id AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text("SELECT COUNT(*) FROM orders WHERE user_id = :user_id AND deleted_at IS NULL")
    try:
        rows = (await db.execute(q, {"user_id": user_id, "limit": limit, "offset": offset})).mappings().all()
        total = int((await db.execute(count_q, {"user_id": user_id})).scalar_one())
    except Exception:
        rows, total = [], 0
    return {
        "user_id": user_id,
        "items": [
            {
                "id": r["id"],
                "status": r["status"],
                "total_amount": float(r["total_amount"] or 0),
                "down_payment_amount": float(r["down_payment_amount"] or 0) if r["down_payment_amount"] else None,
                "created_at": r["created_at"],
                "product_description": r["product_description"],
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/{user_id}/loans")
async def get_user_loans(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = (page - 1) * limit
    q = text(
        """
        SELECT id, loan_number, order_id, status, principal_amount, profit_amount,
               total_repayable, installment_count, created_at
        FROM loans
        WHERE user_id = :user_id AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text("SELECT COUNT(*) FROM loans WHERE user_id = :user_id AND deleted_at IS NULL")
    try:
        rows = (await db.execute(q, {"user_id": user_id, "limit": limit, "offset": offset})).mappings().all()
        total = int((await db.execute(count_q, {"user_id": user_id})).scalar_one())
    except Exception:
        rows, total = [], 0
    return {
        "user_id": user_id,
        "items": [
            {
                "id": r["id"],
                "loan_number": r["loan_number"],
                "order_id": r["order_id"],
                "status": r["status"],
                "principal_amount": float(r["principal_amount"] or 0),
                "profit_amount": float(r["profit_amount"] or 0),
                "total_repayable": float(r["total_repayable"] or 0),
                "installment_count": r["installment_count"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/{user_id}/audit-log")
async def get_user_audit_log(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = (page - 1) * limit
    q = text(
        """
        SELECT id, module, action, target_id, changes, ip_address, request_id, created_at
        FROM audit_trails
        WHERE customer_user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text("SELECT COUNT(*) FROM audit_trails WHERE customer_user_id = :user_id")
    try:
        rows = (await db.execute(q, {"user_id": user_id, "limit": limit, "offset": offset})).mappings().all()
        total = int((await db.execute(count_q, {"user_id": user_id})).scalar_one())
    except Exception:
        rows, total = [], 0
    return {
        "user_id": user_id,
        "items": [
            {
                "id": r["id"],
                "module": r["module"],
                "action": r["action"],
                "target_id": r["target_id"],
                "changes": r["changes"],
                "ip_address": r["ip_address"],
                "request_id": r["request_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }
