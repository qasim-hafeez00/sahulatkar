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
        SELECT id, name, domain, status, partner_type, commission_rate_pct, onboarding_status, created_at,
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
                "partner_type": r["partner_type"],
                "commission_rate_pct": float(r["commission_rate_pct"]) if r["commission_rate_pct"] is not None else None,
                "onboarding_status": r["onboarding_status"],
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
               m.partner_type, m.commission_rate_pct, m.payment_terms_days,
               m.min_volume_commitment_pkr, m.onboarding_status,
               COUNT(DISTINCT o.id) AS order_count,
               COALESCE(SUM(o.total_amount), 0) AS total_gmv
        FROM merchants m
        LEFT JOIN products p ON p.merchant_id = m.id AND p.deleted_at IS NULL
        LEFT JOIN orders o ON o.product_id = p.id AND o.deleted_at IS NULL AND o.status NOT IN ('cancelled','refunded')
        WHERE m.id = :merchant_id AND m.deleted_at IS NULL
        GROUP BY m.id, m.name, m.domain, m.status, m.created_at, m.partner_type,
                 m.commission_rate_pct, m.payment_terms_days, m.min_volume_commitment_pkr, m.onboarding_status
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
        "partner_type": row["partner_type"],
        "commission_rate_pct": float(row["commission_rate_pct"]) if row["commission_rate_pct"] is not None else None,
        "payment_terms_days": row["payment_terms_days"],
        "min_volume_commitment_pkr": float(row["min_volume_commitment_pkr"]) if row["min_volume_commitment_pkr"] is not None else None,
        "onboarding_status": row["onboarding_status"],
        "order_count": int(row["order_count"] or 0),
        "total_gmv": float(row["total_gmv"] or 0),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.put("/merchants/{merchant_id}/status")
async def update_merchant_status(
    merchant_id: int,
    payload: MerchantStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_partners")),
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


# ============================================================================
# Module 10 — partnership terms, performance, onboarding, commissions & payouts
# ============================================================================


class PartnershipTermsRequest(BaseModel):
    partner_type: str = Field(..., pattern="^(direct_integration|affiliate|scraped_only)$")
    commission_rate_pct: float = Field(..., ge=0, le=100)
    payment_terms_days: int = Field(..., gt=0, le=365)
    min_volume_commitment_pkr: float | None = Field(default=None, ge=0)


@router.put("/merchants/{merchant_id}/partnership")
async def update_partnership_terms(
    merchant_id: int,
    payload: PartnershipTermsRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(
        text("SELECT id FROM merchants WHERE id = :id AND deleted_at IS NULL"), {"id": merchant_id}
    )
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MERCHANT_NOT_FOUND")

    await db.execute(
        text(
            """
            UPDATE merchants
            SET partner_type = :partner_type, commission_rate_pct = :commission_rate_pct,
                payment_terms_days = :payment_terms_days, min_volume_commitment_pkr = :min_volume
            WHERE id = :id
            """
        ),
        {
            "partner_type": payload.partner_type,
            "commission_rate_pct": payload.commission_rate_pct,
            "payment_terms_days": payload.payment_terms_days,
            "min_volume": payload.min_volume_commitment_pkr,
            "id": merchant_id,
        },
    )
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_partners",
        action="partnership_terms_updated",
        target_id=merchant_id,
        changes=payload.model_dump(),
    )
    await db.commit()
    return {"merchant_id": merchant_id, "status": "updated"}


@router.get("/merchants/{merchant_id}/performance")
async def merchant_performance(
    merchant_id: int,
    days: int = 30,
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT date, success_rate, avg_checkout_sec, captcha_failure_rate, ban_rate, order_count
                FROM merchant_performance_metrics
                WHERE merchant_id = :merchant_id AND date >= CURRENT_DATE - make_interval(days => :days)
                ORDER BY date ASC
                """
            ),
            {"merchant_id": merchant_id, "days": days},
        )
    ).mappings().all()
    return {
        "series": [
            {
                "date": r["date"].isoformat(),
                "success_rate": float(r["success_rate"]) if r["success_rate"] is not None else None,
                "avg_checkout_sec": r["avg_checkout_sec"],
                "captcha_failure_rate": float(r["captcha_failure_rate"]) if r["captcha_failure_rate"] is not None else None,
                "ban_rate": float(r["ban_rate"]) if r["ban_rate"] is not None else None,
                "order_count": r["order_count"],
            }
            for r in rows
        ]
    }


class OnboardingApplicationRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=20)
    proposed_partner_type: str | None = Field(default=None, pattern="^(direct_integration|affiliate|scraped_only)$")
    proposed_commission_rate_pct: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None


@router.get("/onboarding-applications")
async def list_onboarding_applications(
    status_filter: str | None = None,
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where_sql = "WHERE status = :status_filter" if status_filter else ""
    params: dict = {"status_filter": status_filter} if status_filter else {}
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, merchant_name, domain, contact_name, contact_email, status,
                       proposed_partner_type, proposed_commission_rate_pct, merchant_id, created_at
                FROM merchant_onboarding_applications
                {where_sql}
                ORDER BY created_at DESC
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "merchant_name": r["merchant_name"],
                "domain": r["domain"],
                "contact_name": r["contact_name"],
                "contact_email": r["contact_email"],
                "status": r["status"],
                "proposed_partner_type": r["proposed_partner_type"],
                "proposed_commission_rate_pct": float(r["proposed_commission_rate_pct"]) if r["proposed_commission_rate_pct"] is not None else None,
                "merchant_id": r["merchant_id"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/onboarding-applications", status_code=status.HTTP_201_CREATED)
async def create_onboarding_application(
    payload: OnboardingApplicationRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                INSERT INTO merchant_onboarding_applications (
                    merchant_name, domain, contact_name, contact_email, contact_phone,
                    proposed_partner_type, proposed_commission_rate_pct, notes
                ) VALUES (
                    :merchant_name, :domain, :contact_name, :contact_email, :contact_phone,
                    :proposed_partner_type, :proposed_commission_rate_pct, :notes
                )
                RETURNING id, created_at
                """
            ),
            payload.model_dump(),
        )
    ).mappings().one()
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_partners", action="onboarding_application_created",
        target_id=row["id"], changes={"merchant_name": payload.merchant_name},
    )
    await db.commit()
    return {"id": row["id"], "status": "pending", "created_at": row["created_at"].isoformat()}


class OnboardingDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    notes: str | None = None


@router.post("/onboarding-applications/{application_id}/decision")
async def decide_onboarding_application(
    application_id: int,
    payload: OnboardingDecisionRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    app_row = (
        await db.execute(
            text("SELECT * FROM merchant_onboarding_applications WHERE id = :id"), {"id": application_id}
        )
    ).mappings().one_or_none()
    if not app_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APPLICATION_NOT_FOUND")
    if app_row["status"] not in ("pending", "in_review"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="APPLICATION_ALREADY_DECIDED")

    merchant_id = None
    if payload.decision == "approved":
        merchant_row = (
            await db.execute(
                text(
                    """
                    INSERT INTO merchants (uuid, name, domain, partner_type, commission_rate_pct, onboarding_status, status)
                    VALUES (gen_random_uuid(), :name, :domain, :partner_type, :commission_rate_pct, 'approved', 'active')
                    RETURNING id
                    """
                ),
                {
                    "name": app_row["merchant_name"],
                    "domain": app_row["domain"],
                    "partner_type": app_row["proposed_partner_type"],
                    "commission_rate_pct": app_row["proposed_commission_rate_pct"],
                },
            )
        ).mappings().one()
        merchant_id = merchant_row["id"]

    await db.execute(
        text(
            """
            UPDATE merchant_onboarding_applications
            SET status = :status, notes = COALESCE(:notes, notes), merchant_id = :merchant_id,
                reviewed_by = :reviewed_by, reviewed_at = NOW(), updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "status": payload.decision,
            "notes": payload.notes,
            "merchant_id": merchant_id,
            "reviewed_by": current_admin.id,
            "id": application_id,
        },
    )
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_partners", action=f"onboarding_{payload.decision}",
        target_id=application_id, changes={"merchant_id": merchant_id},
    )
    await db.commit()
    return {"id": application_id, "status": payload.decision, "merchant_id": merchant_id}


@router.get("/merchants/{merchant_id}/commission-summary")
async def merchant_commission_summary(
    merchant_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(commission_amount) FILTER (WHERE status = 'accrued'), 0) AS accrued,
                    COALESCE(SUM(commission_amount) FILTER (WHERE status = 'paid_out'), 0) AS paid_out,
                    COUNT(*) FILTER (WHERE status = 'accrued') AS accrued_count
                FROM merchant_commission_accruals
                WHERE merchant_id = :merchant_id
                """
            ),
            {"merchant_id": merchant_id},
        )
    ).mappings().one()
    payouts = (
        await db.execute(
            text(
                """
                SELECT id, period_start, period_end, total_amount, status, paid_at
                FROM merchant_payouts WHERE merchant_id = :merchant_id ORDER BY created_at DESC LIMIT 10
                """
            ),
            {"merchant_id": merchant_id},
        )
    ).mappings().all()
    return {
        "accrued": float(row["accrued"] or 0),
        "paid_out": float(row["paid_out"] or 0),
        "accrued_count": int(row["accrued_count"] or 0),
        "recent_payouts": [
            {
                "id": p["id"],
                "period_start": p["period_start"].isoformat(),
                "period_end": p["period_end"].isoformat(),
                "total_amount": float(p["total_amount"]),
                "status": p["status"],
                "paid_at": p["paid_at"].isoformat() if p["paid_at"] else None,
            }
            for p in payouts
        ],
    }


class InitiatePayoutRequest(BaseModel):
    period_start: str
    period_end: str


@router.post("/merchants/{merchant_id}/payouts", status_code=status.HTTP_201_CREATED)
async def initiate_merchant_payout(
    merchant_id: int,
    payload: InitiatePayoutRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    accrued_total = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(commission_amount), 0) FROM merchant_commission_accruals
            WHERE merchant_id = :merchant_id AND status = 'accrued'
            """
        ),
        {"merchant_id": merchant_id},
    )
    if not accrued_total or float(accrued_total) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NO_ACCRUED_COMMISSION")

    payout_row = (
        await db.execute(
            text(
                """
                INSERT INTO merchant_payouts (merchant_id, period_start, period_end, total_amount, status, initiated_by)
                VALUES (:merchant_id, :period_start, :period_end, :total_amount, 'pending', :initiated_by)
                RETURNING id, created_at
                """
            ),
            {
                "merchant_id": merchant_id,
                "period_start": payload.period_start,
                "period_end": payload.period_end,
                "total_amount": float(accrued_total),
                "initiated_by": current_admin.id,
            },
        )
    ).mappings().one()

    await db.execute(
        text(
            """
            UPDATE merchant_commission_accruals
            SET status = 'paid_out', payout_id = :payout_id
            WHERE merchant_id = :merchant_id AND status = 'accrued'
            """
        ),
        {"payout_id": payout_row["id"], "merchant_id": merchant_id},
    )
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_partners", action="payout_initiated",
        target_id=payout_row["id"], changes={"merchant_id": merchant_id, "amount": float(accrued_total)},
        severity="critical",
    )
    await db.commit()
    return {"payout_id": payout_row["id"], "total_amount": float(accrued_total), "status": "pending"}
