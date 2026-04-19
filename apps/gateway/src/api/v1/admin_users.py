from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.models.credit import CreditLimitHistory, RiskAssessment
from sk_shared.models.payment import Installment, Loan
from src.core.logging import logger

from src.core.dependencies import get_current_admin, get_current_admin_token_payload, get_db, RequirePermission
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
        # Support searching by phone (partial) or ID (exact/partial)
        if search.isdigit():
            where_clauses.append("(LOWER(phone) LIKE LOWER(:search) OR CAST(id AS TEXT) LIKE :search)")
        else:
            where_clauses.append("LOWER(phone) LIKE LOWER(:search)")
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
    payload: dict = Depends(get_current_admin_token_payload),
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

    # BUG-04 FIX: Return HTTP 404 when user not found, not 200 with null payload
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    permissions = set(payload.get("permissions", []))
    if "all_actions" in permissions:
        permissions.update({"read_user_financials", "manage_kyc_queue"})
    tabs = ["personal", "orders", "activity"]
    if "read_user_financials" in permissions:
        tabs.extend(["financial", "payments"])
    if "manage_kyc_queue" in permissions or "read_user" in permissions:
        tabs.append("kyc")

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
        "tabs": tabs,
    }


@router.get("/{user_id}/financial-summary")
async def get_user_financial_summary(
    user_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_user_financials")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    latest_credit_limit = None
    latest_risk = None
    try:
        active_loans = int(
            (
                await db.execute(
                    text("SELECT COUNT(*) FROM loans WHERE user_id = :uid AND deleted_at IS NULL AND status = 'active'"),
                    {"uid": user_id},
                )
            ).scalar_one()
        )
        overdue_installments = int(
            (
                await db.execute(
                    text("SELECT COUNT(*) FROM installments WHERE user_id = :uid AND deleted_at IS NULL AND status = 'overdue'"),
                    {"uid": user_id},
                )
            ).scalar_one()
        )
        latest_credit_limit = await db.scalar(
            text(
                "SELECT new_limit FROM credit_limit_history WHERE user_id = :uid ORDER BY created_at DESC LIMIT 1"
            ),
            {"uid": user_id},
        )
        latest_risk = (
            await db.execute(
                text(
                    "SELECT risk_band, recommended_limit, assessment_type FROM risk_assessments WHERE user_id = :uid ORDER BY created_at DESC LIMIT 1"
                ),
                {"uid": user_id},
            )
        ).mappings().one_or_none()
    except Exception:
        active_loans, overdue_installments, latest_credit_limit, latest_risk = 0, 0, None, None

    credit_limit = float(latest_risk["recommended_limit"] if latest_risk and latest_risk["recommended_limit"] is not None else latest_credit_limit or 0)
    active_loan_rows = (
        await db.execute(
            text("SELECT COALESCE(SUM(total_outstanding), 0) AS outstanding FROM loans WHERE user_id = :uid AND deleted_at IS NULL AND status = 'active'"),
            {"uid": user_id},
        )
    ).mappings().one_or_none()
    outstanding = float(active_loan_rows["outstanding"] if active_loan_rows else 0)
    available_credit = max(credit_limit - outstanding, 0.0)

    from sk_shared.models.auth import User
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if not user:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    return {
        "user_id": user_id,
        "credit_limit": float(user.credit_limit or 0),
        "available_credit": float(user.available_credit or 0),
        "credit_status": "active" if (user.credit_limit or 0) > 0 else "pending",
        "latest_risk_band": user.risk_band or (latest_risk["risk_band"] if latest_risk else "unknown"),
        "total_outstanding": outstanding,
        "active_loans": active_loans,
        "overdue_installments": overdue_installments,
        "next_review_date": user.next_review_date.isoformat() if user.next_review_date else None,
    }


@router.get("/{user_id}/kyc")
async def get_user_kyc_summary(
    user_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        profile = (
            await db.execute(
                text(
                    "SELECT first_name, last_name, cnic, dob, address FROM customer_profiles WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )
        ).mappings().one_or_none()
        verification = (
            await db.execute(
                text(
                    "SELECT status, rejection_reason, created_at, updated_at FROM user_kyc_verifications WHERE user_id = :uid ORDER BY created_at DESC LIMIT 1"
                ),
                {"uid": user_id},
            )
        ).mappings().one_or_none()
    except Exception as exc:
        logger.warning("KYC summary lookup failed for user %s: %s", user_id, exc)
        profile = None
        verification = None

    # BUG-07 FIX: Decrypt CNIC if it's stored as encrypted bytes
    if profile and profile.get("cnic"):
        raw_cnic = profile["cnic"]
        if isinstance(raw_cnic, (bytes, bytearray)):
            try:
                from src.core.kms import KMSProvider
                profile = dict(profile)
                profile["cnic"] = KMSProvider().decrypt(raw_cnic)
            except Exception as exc:
                logger.warning("CNIC decryption failed for user %s: %s", user_id, exc)
                profile["cnic"] = "DECRYPTION_ERROR"

    return {
        "user_id": user_id,
        "profile": dict(profile) if profile else None,
        "verification": dict(verification) if verification else None,
    }


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
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
    await db.commit()
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
    await db.commit()
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

# ============================================================================
# TASK-22: Admin User Risk History
# ============================================================================

@router.get("/{user_id}/risk-history")
async def get_user_risk_history(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("read_user_financials")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin endpoint to view all risk assessments for a user"""
    offset = (page - 1) * limit
    q = text("""
        SELECT id, risk_band, decision, recommended_limit, assessment_type, created_at
        FROM risk_assessments
        WHERE user_id = :user_id AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    count_q = text("SELECT COUNT(*) FROM risk_assessments WHERE user_id = :user_id AND deleted_at IS NULL")
    try:
        rows = (await db.execute(q, {"user_id": user_id, "limit": limit, "offset": offset})).mappings().all()
        total = int((await db.execute(count_q, {"user_id": user_id})).scalar_one() or 0)
    except Exception:
        rows, total = [], 0
    
    return {
        "user_id": user_id,
        "items": [
            {
                "id": dict(r)["id"],
                "risk_band": dict(r)["risk_band"],
                "decision": dict(r)["decision"],
                "recommended_limit": float(dict(r)["recommended_limit"] or 0),
                "assessment_type": dict(r)["assessment_type"],
                "created_at": dict(r)["created_at"].isoformat() if dict(r)["created_at"] else None,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/{user_id}/risk")
async def get_user_risk_history_alias(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("read_user_financials")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_user_risk_history(
        user_id=user_id,
        page=page,
        limit=limit,
        current_admin=current_admin,
        db=db,
    )


@router.get("/{user_id}/contracts")
async def get_user_contracts(
    user_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.contracts import MurabahaContract, WakalahAgreement

    user = await db.scalar(select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at.is_(None)))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    wakalah_rows = (
        await db.execute(
            select(WakalahAgreement)
            .where(WakalahAgreement.user_id == user_id, WakalahAgreement.deleted_at.is_(None))
            .order_by(WakalahAgreement.created_at.desc())
        )
    ).scalars().all()
    murabaha_rows = (
        await db.execute(
            select(MurabahaContract)
            .where(MurabahaContract.user_id == user_id, MurabahaContract.deleted_at.is_(None))
            .order_by(MurabahaContract.created_at.desc())
        )
    ).scalars().all()

    return {
        "user_id": user_id,
        "wakalah": [
            {
                "id": row.id,
                "order_id": row.order_id,
                "contract_number": row.contract_number,
                "signed_at": row.signed_at.isoformat() if row.signed_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in wakalah_rows
        ],
        "murabaha": [
            {
                "id": row.id,
                "order_id": row.order_id,
                "contract_number": row.contract_number,
                "total_sale_price": float(row.total_sale_price or 0),
                "installment_count": row.installment_count,
                "signed_at": row.signed_at.isoformat() if row.signed_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in murabaha_rows
        ],
    }
