"""Admin Reporting Engine — Phase 4 thin module. Wraps regulatory_reports + Module 9's report builder."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/reports", tags=["Admin Reporting Engine"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("")
async def list_generated_reports(
    report_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_sql = "WHERE r.report_type = :report_type" if report_type else ""
    params: dict = {"limit": limit, "offset": offset}
    if report_type:
        params["report_type"] = report_type

    rows = (
        await db.execute(
            text(
                f"""
                SELECT r.id, r.report_type, r.period, r.generated_at, r.submitted_at,
                       r.reference_number, r.generated_by, a.email AS generated_by_email
                FROM regulatory_reports r
                LEFT JOIN admin_users a ON a.id = r.generated_by
                {where_sql}
                ORDER BY r.generated_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    total = int(
        await db.scalar(
            text(f"SELECT COUNT(*) FROM regulatory_reports r {where_sql}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r["id"],
                "report_type": r["report_type"],
                "period": _iso(r["period"]),
                "generated_at": _iso(r["generated_at"]),
                "submitted_at": _iso(r["submitted_at"]),
                "reference_number": r["reference_number"],
                "generated_by_email": r["generated_by_email"],
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/summary")
async def reports_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text("SELECT report_type, COUNT(*) AS cnt, MAX(generated_at) AS last_generated FROM regulatory_reports GROUP BY report_type")
        )
    ).mappings().all()
    return {
        "by_type": [
            {"report_type": r["report_type"], "count": int(r["cnt"]), "last_generated": _iso(r["last_generated"])}
            for r in rows
        ]
    }
