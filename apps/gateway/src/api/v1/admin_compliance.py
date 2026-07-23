from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, status
from sqlalchemy import func, select, text
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
    charity_q = text(
        """
        SELECT
            COUNT(*) AS allocations_count,
            COALESCE(SUM(late_fee_amount), 0) AS total_late_fee_allocated,
            COALESCE(SUM(CASE WHEN disbursed_at IS NOT NULL THEN late_fee_amount ELSE 0 END), 0) AS total_disbursed
        FROM late_fee_charity_allocations
        WHERE deleted_at IS NULL
        """
    )
    violations_q = text(
        """
        SELECT COUNT(*) AS violations_count
        FROM murabaha_contracts m
        JOIN wakalah_agreements w ON m.order_id = w.order_id
        WHERE m.signed_at < w.signed_at
        AND m.deleted_at IS NULL AND w.deleted_at IS NULL
        """
    )
    row = (await db.execute(charity_q)).mappings().one_or_none() or {
        "allocations_count": 0,
        "total_late_fee_allocated": 0,
        "total_disbursed": 0,
    }
    violations = (await db.execute(violations_q)).scalar() or 0
    return {
        "allocations_count": int(row["allocations_count"] or 0),
        "total_late_fee_allocated": float(row["total_late_fee_allocated"] or 0),
        "total_disbursed": float(row["total_disbursed"] or 0),
        "contract_sequence_violations": int(violations),
        "compliance_status": "compliant" if violations == 0 else "violations_found"
    }


@router.get("/charity-audit")
async def charity_audit_trail(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("read_compliance")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    q = text("""
        SELECT a.id, a.loan_id, a.installment_id, a.late_fee_amount, a.allocated_at,
               a.disbursed_at, a.disbursement_ref, c.name as charity_name
        FROM late_fee_charity_allocations a
        LEFT JOIN charity_organizations c ON a.charity_org_id = c.id
        WHERE a.deleted_at IS NULL
        ORDER BY a.allocated_at DESC
        LIMIT :limit OFFSET :offset
    """)
    count_q = text("SELECT COUNT(*) FROM late_fee_charity_allocations WHERE deleted_at IS NULL")
    
    try:
        rows = (await db.execute(q, {"limit": limit, "offset": offset})).mappings().all()
        total = int((await db.execute(count_q)).scalar_one())
    except Exception:
        rows, total = [], 0
        
    return {
        "items": [
            {
                "id": dict(r)["id"],
                "loan_id": dict(r)["loan_id"],
                "installment_id": dict(r)["installment_id"],
                "late_fee_amount": float(dict(r)["late_fee_amount"] or 0),
                "allocated_at": _iso(dict(r)["allocated_at"]),
                "disbursed_at": _iso(dict(r)["disbursed_at"]) if dict(r)["disbursed_at"] else None,
                "disbursement_ref": dict(r)["disbursement_ref"],
                "charity_name": dict(r)["charity_name"],
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
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


# ============================================================================
# Module 8 — critical-action feed, regulatory calendar, data-privacy panel
# ============================================================================


@router.get("/critical-actions")
async def critical_actions_feed(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("read_audit")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    rows = (
        await db.execute(
            select(AuditTrail)
            .where(AuditTrail.severity == "critical")
            .order_by(AuditTrail.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    total = int(
        await db.scalar(
            select(func.count()).select_from(AuditTrail).where(AuditTrail.severity == "critical")
        )
        or 0
    )
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
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


# Regulatory filing cadence (days between filings) for each report_type the
# regulatory_reports.report_type CHECK constraint allows.
_FILING_CADENCE_DAYS = {
    "monthly_bnpl": 30,
    "annual_kyc": 365,
    "aml_sar": 30,
    "secp_return": 90,
    "sbp_rcd1": 30,
    "fbr_gst3": 30,
}


@router.get("/regulatory-calendar")
async def regulatory_calendar(
    current_admin: AdminUser = Depends(RequirePermission("read_compliance")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT ON (report_type) report_type, period, generated_at, submitted_at, reference_number
                FROM regulatory_reports
                ORDER BY report_type, generated_at DESC
                """
            )
        )
    ).mappings().all()
    latest_by_type = {r["report_type"]: r for r in rows}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    calendar = []
    for report_type, cadence_days in _FILING_CADENCE_DAYS.items():
        latest = latest_by_type.get(report_type)
        last_filed_at = latest["generated_at"] if latest else None
        next_due = (last_filed_at + timedelta(days=cadence_days)) if last_filed_at else now
        calendar.append(
            {
                "report_type": report_type,
                "cadence_days": cadence_days,
                "last_filed_at": _iso(last_filed_at),
                "last_reference_number": latest["reference_number"] if latest else None,
                "next_due_at": _iso(next_due),
                "status": "overdue" if next_due < now else "upcoming",
            }
        )

    return {"calendar": sorted(calendar, key=lambda c: c["next_due_at"])}


@router.get("/data-privacy")
async def data_privacy_panel(
    current_admin: AdminUser = Depends(RequirePermission("read_compliance")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    deletion_rows = (
        await db.execute(
            text(
                """
                SELECT status, COUNT(*) AS cnt
                FROM data_deletion_requests
                GROUP BY status
                """
            )
        )
    ).mappings().all()
    consent_rows = (
        await db.execute(
            text(
                """
                SELECT consent_type, decision, COUNT(*) AS cnt
                FROM user_consent_records
                GROUP BY consent_type, decision
                """
            )
        )
    ).mappings().all()
    recent_requests = (
        await db.execute(
            text(
                """
                SELECT id, user_id, request_type, status, created_at
                FROM data_deletion_requests
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
        )
    ).mappings().all()

    consent_summary: dict = {}
    for r in consent_rows:
        consent_summary.setdefault(r["consent_type"], {})[r["decision"]] = int(r["cnt"])

    return {
        "deletion_requests_by_status": {r["status"]: int(r["cnt"]) for r in deletion_rows},
        "consent_summary": consent_summary,
        "recent_deletion_requests": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "request_type": r["request_type"],
                "status": r["status"],
                "created_at": _iso(r["created_at"]),
            }
            for r in recent_requests
        ],
    }
