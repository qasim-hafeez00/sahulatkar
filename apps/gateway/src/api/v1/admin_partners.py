from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/partners", tags=["Admin Partners"])


class MerchantStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|suspended)$")


@router.get("/merchants")
async def list_merchants(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = ["deleted_at IS NULL"]
    params: dict = {"limit": limit, "offset": offset}

    if search:
        where_clauses.append("(LOWER(name) LIKE LOWER(:search) OR LOWER(domain) LIKE LOWER(:search))")
        params["search"] = f"%{search}%"
    if status:
        where_clauses.append("status = :status")
        params["status"] = status

    where_sql = " AND ".join(where_clauses)
    q = text(
        f"""
        SELECT id, name, domain, status, created_at,
               (SELECT COUNT(*) FROM products p WHERE p.merchant_id = merchants.id AND p.deleted_at IS NULL) AS product_count
        FROM merchants
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text(f"SELECT COUNT(*) FROM merchants WHERE {where_sql}")

    try:
        rows = (await db.execute(q, params)).mappings().all()
        total = int((await db.execute(count_q, params)).scalar_one() or 0)
    except Exception:
        rows, total = [], 0

    return {
        "items": [
            {
                "id": r["id"],
                "name": r["name"],
                "domain": r["domain"],
                "status": r["status"],
                "product_count": int(r["product_count"] or 0),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/merchants/{merchant_id}")
async def get_merchant_detail(
    merchant_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT m.id, m.name, m.domain, m.status, m.created_at,
               COUNT(DISTINCT o.id) AS order_count,
               COALESCE(SUM(o.total_amount), 0) AS total_gmv
        FROM merchants m
        LEFT JOIN products p ON p.merchant_id = m.id AND p.deleted_at IS NULL
        LEFT JOIN orders o ON o.product_id = p.id AND o.deleted_at IS NULL AND o.status NOT IN ('cancelled','refunded')
        WHERE m.id = :merchant_id AND m.deleted_at IS NULL
        GROUP BY m.id, m.name, m.domain, m.status, m.created_at
        """
    )
    try:
        row = (await db.execute(q, {"merchant_id": merchant_id})).mappings().one_or_none()
    except Exception:
        row = None

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MERCHANT_NOT_FOUND")

    return {
        "id": row["id"],
        "name": row["name"],
        "domain": row["domain"],
        "status": row["status"],
        "order_count": int(row["order_count"] or 0),
        "total_gmv": float(row["total_gmv"] or 0),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.put("/merchants/{merchant_id}/status")
async def update_merchant_status(
    merchant_id: int,
    payload: MerchantStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await db.execute(
            text("UPDATE merchants SET status = :status WHERE id = :merchant_id AND deleted_at IS NULL"),
            {"status": payload.status, "merchant_id": merchant_id},
        )
        row = (await db.execute(
            text("SELECT id, name, status FROM merchants WHERE id = :merchant_id AND deleted_at IS NULL"),
            {"merchant_id": merchant_id},
        )).mappings().one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"MERCHANTS_TABLE_UNAVAILABLE: {exc}")

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MERCHANT_NOT_FOUND")

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_partners",
        action="merchant_status_updated",
        target_id=merchant_id,
        changes={"status": payload.status},
    )
    await db.commit()
    return {"merchant_id": row["id"], "name": row["name"], "status": row["status"]}
