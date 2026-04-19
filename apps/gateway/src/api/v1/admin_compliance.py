from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.models.audit import AuditTrail
from src.core.dependencies import (
    RequirePermission,
    get_current_admin,
    get_current_admin_token_payload,
    get_db,
)

router = APIRouter(prefix="/admin/compliance", tags=["Admin Compliance"])
audit_router = APIRouter(prefix="/admin", tags=["Admin Compliance"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _require_any_permission(payload: dict, allowed_permissions: set[str]) -> None:
    permissions = set(payload.get("permissions", []))
    if "all_actions" in permissions:
        return
    if permissions.intersection(allowed_permissions):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission")


@audit_router.get("/audit-trail")
async def global_audit_trail(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_audit")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit

    stmt = select(AuditTrail)
    if module:
        stmt = stmt.where(AuditTrail.module == module)
    if action:
        stmt = stmt.where(AuditTrail.action == action)

    rows = (
        await db.execute(stmt.order_by(AuditTrail.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()

    return {
        "items": [
            {
                "id": row.id,
                "admin_user_id": row.admin_user_id,
                "customer_user_id": row.customer_user_id,
                "module": row.module,
                "action": row.action,
                "target_id": row.target_id,
                "changes": row.changes,
                "ip_address": row.ip_address,
                "request_id": row.request_id,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ],
        "pagination": {"page": page, "limit": limit},
    }


@router.get("/audit-trail")
async def compliance_audit_trail(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    module: str | None = Query(default=None),
    action: str | None = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_audit")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await global_audit_trail(
        page=page,
        limit=limit,
        module=module,
        action=action,
        current_admin=current_admin,
        db=db,
    )


@router.get("/shariah-audit")
async def shariah_audit_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_compliance")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT
            COUNT(*) AS allocations_count,
            COALESCE(SUM(late_fee_amount), 0) AS total_late_fee_allocated,
            COALESCE(SUM(CASE WHEN disbursed_at IS NOT NULL THEN late_fee_amount ELSE 0 END), 0) AS total_disbursed
        FROM late_fee_charity_allocations
        WHERE deleted_at IS NULL
        """
    )
    row = (await db.execute(q)).mappings().one_or_none() or {
        "allocations_count": 0,
        "total_late_fee_allocated": 0,
        "total_disbursed": 0,
    }
    return {
        "allocations_count": int(row["allocations_count"] or 0),
        "total_late_fee_allocated": float(row["total_late_fee_allocated"] or 0),
        "total_disbursed": float(row["total_disbursed"] or 0),
    }


@router.get("/charity-report")
async def charity_report(
    current_admin: AdminUser = Depends(RequirePermission("read_compliance")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = text(
        """
        SELECT
            c.name,
            COUNT(a.id) AS allocations_count,
            COALESCE(SUM(a.late_fee_amount), 0) AS allocated_amount,
            COALESCE(SUM(CASE WHEN a.disbursed_at IS NOT NULL THEN a.late_fee_amount ELSE 0 END), 0) AS disbursed_amount
        FROM charity_organizations c
        LEFT JOIN late_fee_charity_allocations a ON a.charity_org_id = c.id AND a.deleted_at IS NULL
        WHERE c.deleted_at IS NULL
        GROUP BY c.name
        ORDER BY c.name ASC
        """
    )
    rows = (await db.execute(q)).mappings().all()
    return {
        "items": [
            {
                "charity_name": row["name"],
                "allocations_count": int(row["allocations_count"] or 0),
                "allocated_amount": float(row["allocated_amount"] or 0),
                "disbursed_amount": float(row["disbursed_amount"] or 0),
            }
            for row in rows
        ]
    }


@router.get("/financial-summary")
async def financial_summary(
    current_admin: AdminUser = Depends(get_current_admin),
    payload: dict = Depends(get_current_admin_token_payload),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_any_permission(payload, {"read_financials", "read_reports"})

    q = text(
        """
        SELECT
            COALESCE(SUM(amount), 0) AS total_payments,
            COUNT(*) AS transactions_count
        FROM payment_transactions
        WHERE deleted_at IS NULL
        """
    )
    row = (await db.execute(q)).mappings().one_or_none() or {"total_payments": 0, "transactions_count": 0}
    return {
        "total_payments": float(row["total_payments"] or 0),
        "transactions_count": int(row["transactions_count"] or 0),
    }


@router.get("/reconciliation")
async def reconciliation_summary(
    current_admin: AdminUser = Depends(get_current_admin),
    payload: dict = Depends(get_current_admin_token_payload),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_any_permission(payload, {"read_reconciliation", "read_reports"})

    q = text(
        """
        SELECT
            COUNT(*) AS total_txns,
            SUM(CASE WHEN reconciled_at IS NOT NULL THEN 1 ELSE 0 END) AS reconciled_txns,
            SUM(CASE WHEN reconciled_at IS NULL THEN 1 ELSE 0 END) AS unreconciled_txns
        FROM payment_transactions
        WHERE deleted_at IS NULL
        """
    )
    row = (await db.execute(q)).mappings().one_or_none() or {
        "total_txns": 0,
        "reconciled_txns": 0,
        "unreconciled_txns": 0,
    }
    return {
        "total_transactions": int(row["total_txns"] or 0),
        "reconciled_transactions": int(row["reconciled_txns"] or 0),
        "unreconciled_transactions": int(row["unreconciled_txns"] or 0),
    }
