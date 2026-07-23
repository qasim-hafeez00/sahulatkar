"""Admin Financial Operations — Module 6 (P&L, credit loss, tax summary)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.api.v1.admin_system import get_system_parameters
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/finance", tags=["Admin Financial Ops"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("/pnl")
async def profit_and_loss(
    months: int = 6,
    current_admin: AdminUser = Depends(RequirePermission("read_financials")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    TO_CHAR(o.created_at, 'YYYY-MM') AS month,
                    COALESCE(SUM(o.platform_profit), 0) AS platform_profit,
                    COALESCE(SUM(o.product_cost), 0) AS product_cost,
                    COALESCE(SUM(o.total_amount), 0) AS gmv
                FROM orders o
                WHERE o.deleted_at IS NULL
                  AND o.status NOT IN ('cancelled', 'refunded')
                  AND o.created_at >= NOW() - make_interval(months => :months)
                GROUP BY month
                ORDER BY month ASC
                """
            ),
            {"months": months},
        )
    ).mappings().all()

    late_fee_income = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(late_fee_amount), 0) FROM installments
            WHERE deleted_at IS NULL AND status = 'paid' AND late_fee_waived = false
              AND paid_at >= NOW() - make_interval(months => :months)
            """
        ),
        {"months": months},
    )
    charity_allocated = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(late_fee_amount), 0) FROM late_fee_charity_allocations
            WHERE deleted_at IS NULL AND allocated_at >= NOW() - make_interval(months => :months)
            """
        ),
        {"months": months},
    )

    series = [
        {
            "month": r["month"],
            "gmv": float(r["gmv"] or 0),
            "platform_profit": float(r["platform_profit"] or 0),
            "product_cost": float(r["product_cost"] or 0),
            "net_margin": float(r["platform_profit"] or 0) - float(r["product_cost"] or 0),
        }
        for r in rows
    ]
    total_platform_profit = sum(s["platform_profit"] for s in series)
    total_product_cost = sum(s["product_cost"] for s in series)

    return {
        "series": series,
        "totals": {
            "gmv": sum(s["gmv"] for s in series),
            "platform_profit": total_platform_profit,
            "product_cost": total_product_cost,
            "late_fee_income": float(late_fee_income or 0),
            "charity_allocated": float(charity_allocated or 0),
            "net_income": total_platform_profit - total_product_cost + float(late_fee_income or 0),
        },
    }


@router.get("/credit-loss")
async def credit_loss(
    current_admin: AdminUser = Depends(RequirePermission("read_financials")),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'defaulted') AS defaulted_count,
                    COALESCE(SUM(total_outstanding) FILTER (WHERE status = 'defaulted'), 0) AS defaulted_outstanding,
                    COUNT(*) FILTER (WHERE status = 'written_off') AS written_off_count,
                    COALESCE(SUM(total_outstanding) FILTER (WHERE status = 'written_off'), 0) AS written_off_amount,
                    COUNT(*) FILTER (WHERE status IN ('active', 'partially_paid')) AS active_count,
                    COALESCE(SUM(total_outstanding) FILTER (WHERE status IN ('active', 'partially_paid')), 0) AS active_outstanding
                FROM loans
                WHERE deleted_at IS NULL
                """
            )
        )
    ).mappings().one()

    params = await get_system_parameters(current_admin=current_admin, db=db, redis=redis)
    provision_rate = float(params["parameters"].get("credit_loss_provision_rate_pct", 25.0))
    at_risk_outstanding = float(row["defaulted_outstanding"] or 0)
    provision_estimate = round(at_risk_outstanding * provision_rate / 100, 2)

    total_outstanding = float(row["active_outstanding"] or 0) + at_risk_outstanding
    default_rate_pct = (
        round(at_risk_outstanding / total_outstanding * 100, 2) if total_outstanding > 0 else 0.0
    )

    return {
        "defaulted_count": int(row["defaulted_count"] or 0),
        "defaulted_outstanding": at_risk_outstanding,
        "written_off_count": int(row["written_off_count"] or 0),
        "written_off_amount": float(row["written_off_amount"] or 0),
        "active_count": int(row["active_count"] or 0),
        "active_outstanding": float(row["active_outstanding"] or 0),
        "provision_rate_pct": provision_rate,
        "provision_estimate": provision_estimate,
        "default_rate_pct": default_rate_pct,
    }


@router.get("/tax-summary")
async def tax_summary(
    months: int = 1,
    current_admin: AdminUser = Depends(RequirePermission("read_financials")),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    platform_profit = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(platform_profit), 0) FROM orders
            WHERE deleted_at IS NULL AND status NOT IN ('cancelled', 'refunded')
              AND created_at >= NOW() - make_interval(months => :months)
            """
        ),
        {"months": months},
    )
    params = await get_system_parameters(current_admin=current_admin, db=db, redis=redis)
    gst_rate = float(params["parameters"].get("gst_rate_pct", 18.0))
    taxable_income = float(platform_profit or 0)
    gst_liability = round(taxable_income * gst_rate / 100, 2)

    return {
        "period_months": months,
        "taxable_income": taxable_income,
        "gst_rate_pct": gst_rate,
        "gst_liability": gst_liability,
    }


@router.post("/tax-summary/generate", status_code=status.HTTP_201_CREATED)
async def generate_tax_summary_filing(
    request: Request,
    months: int = 1,
    current_admin: AdminUser = Depends(RequirePermission("manage_financials")),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    """Snapshot the current tax summary as an FBR GST-return filing record."""
    summary = await tax_summary(months=months, current_admin=current_admin, db=db, redis=redis)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO regulatory_reports (report_type, period, reference_number, generated_by)
                VALUES ('fbr_gst3', date_trunc('month', CURRENT_DATE), :ref, :admin_id)
                RETURNING id, reference_number, generated_at
                """
            ),
            {
                "ref": f"GST3-{current_admin.id}-{int(summary['gst_liability'] * 100)}",
                "admin_id": current_admin.id,
            },
        )
    ).mappings().one()

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_finance",
        action="tax_summary_filed",
        target_id=row["id"],
        changes=summary,
    )
    await db.commit()
    return {
        "regulatory_report_id": row["id"],
        "reference_number": row["reference_number"],
        "generated_at": _iso(row["generated_at"]),
        "summary": summary,
    }
