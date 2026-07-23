from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.admin import AdminApprovalRequest
from sk_shared.models.auth import AdminUser
from sk_shared.models.credit import CreditLimitHistory, RiskAssessment
from sk_shared.models.payment import Installment, Loan
from sk_shared.security import get_password_hash
from src.core.logging import logger

from src.core.dependencies import get_current_admin, get_current_admin_token_payload, get_db, get_redis, RequirePermission
from src.core.audit import record_audit_event
from sk_shared.redis_client import RedisClient
from sk_shared.constants import QueueName
import json

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])

CREDIT_LIMIT_APPROVAL_THRESHOLD_PKR = 100_000
CLOSURE_COOLING_OFF_DAYS = 30


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
        SELECT u.id, u.phone, u.status, u.created_at, u.failed_login_attempts, u.locked_until,
               u.credit_limit, u.available_credit, u.risk_band,
               (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS total_orders
        FROM users u
        WHERE {where_clause}
        ORDER BY {sort_column} {sort_order}
        LIMIT :limit OFFSET :offset
        """.format(where_clause=" AND ".join(where_clauses), sort_column=sort_column, sort_order=sort_order)
    )

    count_query = text(
        "SELECT COUNT(*) FROM users u WHERE {where_clause}".format(where_clause=" AND ".join(where_clauses))
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
                "credit_limit": float(row["credit_limit"] or 0),
                "available_credit": float(row["available_credit"] or 0),
                "risk_band": row["risk_band"],
                "total_orders": int(row["total_orders"] or 0),
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
        },
    }


@router.get("/closure-requests")
async def list_closure_requests(
    status_filter: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_sql = "WHERE d.status = :status_filter" if status_filter else ""
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        params["status_filter"] = status_filter

    rows = (
        await db.execute(
            text(
                f"""
                SELECT d.id, d.user_id, d.request_type, d.status, d.verification_method,
                       d.verified_at, d.executed_at, d.created_at,
                       u.first_name, u.last_name, u.phone
                FROM data_deletion_requests d
                LEFT JOIN users u ON u.id = d.user_id
                {where_sql}
                ORDER BY d.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "user_name": " ".join(filter(None, [r["first_name"], r["last_name"]])) or None,
                "user_phone": r["phone"],
                "request_type": r["request_type"],
                "status": r["status"],
                "verification_method": r["verification_method"],
                "verified_at": r["verified_at"].isoformat() if r["verified_at"] else None,
                "executed_at": r["executed_at"].isoformat() if r["executed_at"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit},
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


async def _revoke_all_user_sessions(user_id: int, redis: RedisClient) -> int:
    """Revoke all active Redis session keys for a user. Returns count revoked."""
    from sk_shared.models.auth import UserSession
    if not hasattr(redis, "redis"):
        return 0
    sessions_key = f"sk:auth:user_sessions:{user_id}"
    hashes = await redis.redis.smembers(sessions_key)
    count = 0
    for h in hashes:
        token_hash = h.decode() if isinstance(h, bytes) else str(h)
        await redis.delete(f"sk:auth:session:{token_hash}")
        count += 1
    await redis.delete(sessions_key)
    return count


@router.put("/{user_id}/status")
async def update_user_status(
    user_id: int,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    await db.execute(
        text("UPDATE users SET status = :status WHERE id = :user_id AND deleted_at IS NULL"),
        {"status": payload.status, "user_id": user_id},
    )
    row = (
        await db.execute(
            text("SELECT id, status FROM users WHERE id = :user_id AND deleted_at IS NULL"),
            {"user_id": user_id},
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
        severity="critical" if payload.status in ("suspended", "blocked") else "info",
    )

    # SEC-05: Immediately revoke all active sessions when suspending or blocking
    sessions_revoked = 0
    if payload.status in ("suspended", "blocked"):
        sessions_revoked = await _revoke_all_user_sessions(user_id, redis)
        # Also mark all UserSession rows as revoked in DB
        from datetime import datetime, timezone
        from sqlalchemy import update as sql_update
        from sk_shared.models.auth import UserSession
        await db.execute(
            sql_update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )

    if hasattr(redis, "redis"):
        notification_event = json.dumps(
            {
                "event": "account.status_changed",
                "user_id": user_id,
                "new_status": payload.status,
                "admin_id": current_admin.id,
            }
        )
        await redis.redis.lpush(QueueName.NOTIFICATION_SMS, notification_event)

    await db.commit()
    return {"user_id": row["id"], "status": row["status"], "sessions_revoked": sessions_revoked}


@router.put("/{user_id}/credit-limit")
async def update_user_credit_limit(
    user_id: int,
    payload: UpdateCreditLimitRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("update_user")),
    db: AsyncSession = Depends(get_db),
):
    # BUG-04 FIX: Use ORM update + re-fetch pattern instead of raw RETURNING (not portable to SQLite)
    from sk_shared.models.auth import User as UserModel
    try:
        user_obj = await db.scalar(select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at.is_(None)))
        if user_obj is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

        if payload.new_limit > CREDIT_LIMIT_APPROVAL_THRESHOLD_PKR:
            approval = AdminApprovalRequest(
                request_type="credit_limit_increase",
                entity_type="user",
                entity_id=user_id,
                requested_by=current_admin.id,
                payload={"new_limit": payload.new_limit, "previous_limit": float(user_obj.credit_limit)},
                reason=payload.reason,
            )
            db.add(approval)
            await db.flush()
            await record_audit_event(
                db=db,
                request=request,
                admin_user_id=current_admin.id,
                module="admin_users",
                action="credit_limit_approval_requested",
                target_id=user_id,
                changes={"new_limit": payload.new_limit, "reason": payload.reason, "approval_request_id": approval.id},
                severity="critical",
            )
            await db.commit()
            return {
                "user_id": user_id,
                "approval_required": True,
                "approval_request_id": approval.id,
                "status": "pending_approval",
            }

        user_obj.credit_limit = payload.new_limit
        user_obj.available_credit = payload.new_limit
        row = {"id": user_obj.id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=f"CREDIT_LIMIT_COLUMNS_MISSING: {exc}")

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
    return {"user_id": row["id"], "new_limit": payload.new_limit, "approval_required": False}


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


@router.get("/{user_id}/installments")
async def get_user_installments(
    user_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("read_user_financials")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = (page - 1) * limit
    q = text(
        """
        SELECT i.id, i.loan_id, i.installment_number, i.total_amount, i.paid_amount,
               i.due_date, i.paid_at, i.status, i.days_overdue, i.late_fee_amount,
               l.loan_number, l.order_id
        FROM installments i
        JOIN loans l ON i.loan_id = l.id
        WHERE i.user_id = :user_id AND i.deleted_at IS NULL
        ORDER BY i.due_date ASC
        LIMIT :limit OFFSET :offset
        """
    )
    count_q = text("SELECT COUNT(*) FROM installments WHERE user_id = :user_id AND deleted_at IS NULL")

    rows = (await db.execute(q, {"user_id": user_id, "limit": limit, "offset": offset})).mappings().all()
    total = int((await db.execute(count_q, {"user_id": user_id})).scalar_one() or 0)

    return {
        "user_id": user_id,
        "items": [
            {
                "id": r["id"],
                "loan_id": r["loan_id"],
                "loan_number": r["loan_number"],
                "order_id": r["order_id"],
                "installment_number": r["installment_number"],
                "total_amount": float(r["total_amount"] or 0),
                "paid_amount": float(r["paid_amount"] or 0),
                "due_date": r["due_date"],
                "paid_at": r["paid_at"],
                "status": r["status"],
                "days_overdue": r["days_overdue"],
                "late_fee_amount": float(r["late_fee_amount"] or 0),
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


# ============================================================================
# GAP-06, GAP-08: Admin User Devices & Lockout Reset
# ============================================================================

@router.get("/{user_id}/devices")
async def get_user_devices(
    user_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sk_shared.models.auth import UserDevice
    
    q = text("""
        SELECT id, device_token, platform, is_active, last_used_at, created_at
        FROM user_devices
        WHERE user_id = :user_id
        ORDER BY last_used_at DESC NULLS LAST, created_at DESC
    """)
    try:
        rows = (await db.execute(q, {"user_id": user_id})).mappings().all()
    except Exception:
        rows = []
    
    return {
        "user_id": user_id,
        "items": [
            {
                "id": dict(r)["id"],
                "device_token": dict(r)["device_token"],
                "platform": dict(r)["platform"],
                "is_active": dict(r)["is_active"],
                "last_used_at": dict(r)["last_used_at"].isoformat() if dict(r)["last_used_at"] else None,
                "created_at": dict(r)["created_at"].isoformat() if dict(r)["created_at"] else None,
            }
            for r in rows
        ]
    }

@router.post("/{user_id}/force-logout")
async def force_logout_user(
    user_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    from datetime import datetime, timezone
    from sqlalchemy import update as sql_update
    from sk_shared.models.auth import User as UserModel, UserSession

    user_obj = await db.scalar(select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at.is_(None)))
    if not user_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    sessions_revoked = await _revoke_all_user_sessions(user_id, redis)
    await db.execute(
        sql_update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="force_logout",
        target_id=user_id,
        changes={"sessions_revoked": sessions_revoked},
    )
    await db.commit()
    return {"user_id": user_id, "sessions_revoked": sessions_revoked}


@router.post("/{user_id}/reset-failed-attempts")
async def reset_user_failed_attempts(
    user_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("update_user")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sk_shared.models.auth import User
    
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")
        
    old_attempts = user.failed_login_attempts
    old_locked_until = user.locked_until
    
    user.failed_login_attempts = 0
    user.locked_until = None
    
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="reset_failed_attempts",
        target_id=user.id,
        changes={
            "old_failed_attempts": old_attempts,
            "old_locked_until": old_locked_until.isoformat() if old_locked_until else None,
        },
    )
    
    await db.commit()
    return {"user_id": user.id, "status": "reset_successful"}


# ============================================================================
# Module 2 — create, bulk actions, closure workflow
# ============================================================================


class CreateUserRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+92[0-9]{10}$")
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    initial_status: Literal["active", "pending_kyc"] = "pending_kyc"
    initial_credit_limit: float = Field(default=0, ge=0)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: CreateUserRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sk_shared.models.auth import User as UserModel
    import secrets
    import string

    existing = await db.scalar(select(UserModel).where(UserModel.phone == payload.phone))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PHONE_ALREADY_REGISTERED")

    temp_password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    user = UserModel(
        phone=payload.phone,
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=get_password_hash(temp_password),
        status=payload.initial_status,
        credit_limit=payload.initial_credit_limit,
        available_credit=payload.initial_credit_limit,
    )
    db.add(user)
    await db.flush()

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="create_user",
        target_id=user.id,
        changes={"phone": payload.phone, "initial_status": payload.initial_status},
    )
    await db.commit()
    return {
        "id": user.id,
        "phone": user.phone,
        "status": user.status,
        "temp_password": temp_password,
    }


class BulkUserActionRequest(BaseModel):
    user_ids: list[int] = Field(..., min_length=1, max_length=200)
    action: Literal["suspend", "activate", "block"]
    reason: str = Field(..., min_length=3, max_length=255)


@router.post("/bulk")
async def bulk_user_action(
    payload: BulkUserActionRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    status_map = {"suspend": "suspended", "activate": "active", "block": "blocked"}
    new_status = status_map[payload.action]

    result = await db.execute(
        text(
            """
            UPDATE users SET status = :new_status
            WHERE id = ANY(:user_ids) AND deleted_at IS NULL
            RETURNING id
            """
        ),
        {"new_status": new_status, "user_ids": payload.user_ids},
    )
    updated_ids = [row[0] for row in result.fetchall()]

    if payload.action in ("suspend", "block"):
        for uid in updated_ids:
            await _revoke_all_user_sessions(uid, redis)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="bulk_status_update",
        target_id=None,
        changes={"user_ids": updated_ids, "new_status": new_status, "reason": payload.reason},
        severity="critical" if new_status in ("suspended", "blocked") else "info",
    )
    await db.commit()
    return {"updated_count": len(updated_ids), "updated_ids": updated_ids, "new_status": new_status}


class ClosureRequestBody(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/{user_id}/closure-request", status_code=status.HTTP_201_CREATED)
async def request_user_closure(
    user_id: int,
    payload: ClosureRequestBody,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    from datetime import timedelta

    from sk_shared.models.auth import User as UserModel

    user = await db.scalar(select(UserModel).where(UserModel.id == user_id, UserModel.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    existing = (
        await db.execute(
            text(
                "SELECT id FROM data_deletion_requests WHERE user_id = :uid AND status IN ('pending','verified','in_progress')"
            ),
            {"uid": user_id},
        )
    ).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CLOSURE_ALREADY_PENDING")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO data_deletion_requests (user_id, request_type, verification_method, status)
                VALUES (:uid, 'erasure', 'admin_initiated', 'pending')
                RETURNING id, created_at
                """
            ),
            {"uid": user_id},
        )
    ).mappings().one()

    user.status = "suspended"
    sessions_revoked = await _revoke_all_user_sessions(user_id, redis)
    eligible_at = row["created_at"] + timedelta(days=CLOSURE_COOLING_OFF_DAYS)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="closure_requested",
        target_id=user_id,
        changes={"reason": payload.reason, "eligible_execution_at": eligible_at.isoformat()},
        severity="critical",
    )
    await db.commit()
    return {
        "closure_request_id": row["id"],
        "user_id": user_id,
        "status": "pending",
        "cooling_off_days": CLOSURE_COOLING_OFF_DAYS,
        "eligible_execution_at": eligible_at.isoformat(),
        "sessions_revoked": sessions_revoked,
    }


@router.post("/closure-requests/{request_id}/execute")
async def execute_closure_request(
    request_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    payload: dict = Depends(get_current_admin_token_payload),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import datetime, timedelta, timezone

    row = (
        await db.execute(
            text("SELECT id, user_id, status, created_at FROM data_deletion_requests WHERE id = :id"),
            {"id": request_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLOSURE_REQUEST_NOT_FOUND")
    if row["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CLOSURE_REQUEST_ALREADY_DECIDED")

    eligible_at = row["created_at"] + timedelta(days=CLOSURE_COOLING_OFF_DAYS)
    is_super_admin = payload.get("role") == "super_admin"
    if datetime.now(timezone.utc).replace(tzinfo=None) < eligible_at and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"COOLING_OFF_PERIOD_ACTIVE: eligible at {eligible_at.isoformat()}",
        )

    # Anonymize rather than hard-delete — preserves referential integrity for
    # historical orders/ledger entries while satisfying the erasure request.
    anon_phone = f"deleted-{row['user_id']}"
    await db.execute(
        text(
            """
            UPDATE users
            SET phone = :anon_phone, first_name = NULL, last_name = NULL,
                password_hash = NULL, status = 'closed'
            WHERE id = :user_id
            """
        ),
        {"anon_phone": anon_phone, "user_id": row["user_id"]},
    )
    await db.execute(
        text(
            """
            UPDATE data_deletion_requests
            SET status = 'completed', executed_at = NOW(), tables_cleared = ARRAY['users']
            WHERE id = :id
            """
        ),
        {"id": request_id},
    )

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_users",
        action="closure_executed",
        target_id=row["user_id"],
        changes={"closure_request_id": request_id},
        severity="critical",
    )
    await db.commit()
    return {"closure_request_id": request_id, "user_id": row["user_id"], "status": "completed"}
