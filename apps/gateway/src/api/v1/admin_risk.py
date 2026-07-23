"""Admin Risk & Blacklist Management — GAP-E from the production audit."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal, Optional

from sk_shared.models.auth import AdminUser
from sk_shared.models.admin import RiskBlacklist
from src.api.v1.admin_system import (
    CREDIT_POLICY_KEYS,
    UpdateParametersRequest,
    get_system_parameters,
    update_system_parameters,
)
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/risk", tags=["Admin Risk"])


class BlacklistCreateRequest(BaseModel):
    entry_type: Literal["user", "device", "ip", "phone"]
    value: str = Field(..., min_length=1, max_length=255)
    reason: str = Field(..., min_length=3, max_length=500)
    user_id: Optional[int] = None

    @property
    def _validated(self):
        return self

    def model_post_init(self, __context) -> None:
        if self.entry_type == "phone":
            import re
            if not re.match(r"^\+[0-9]{7,15}$", self.value):
                raise ValueError("phone blacklist value must be a valid E.164 phone number")


@router.get("/blacklist")
async def list_blacklist(
    entry_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    query = select(RiskBlacklist).where(RiskBlacklist.deleted_at.is_(None))
    if entry_type:
        query = query.where(RiskBlacklist.entry_type == entry_type)

    rows = (
        await db.execute(
            query.order_by(RiskBlacklist.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    total = int(
        await db.scalar(
            select(func.count(RiskBlacklist.id)).where(
                RiskBlacklist.deleted_at.is_(None),
                RiskBlacklist.entry_type == entry_type if entry_type else True,
            )
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r.id,
                "entry_type": r.entry_type,
                "value": r.value,
                "reason": r.reason,
                "user_id": r.user_id,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.post("/blacklist", status_code=status.HTTP_201_CREATED)
async def add_to_blacklist(
    payload: BlacklistCreateRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.scalar(
        select(RiskBlacklist).where(
            RiskBlacklist.entry_type == payload.entry_type,
            RiskBlacklist.value == payload.value,
            RiskBlacklist.deleted_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="BLACKLIST_ENTRY_EXISTS")

    row = RiskBlacklist(
        entry_type=payload.entry_type,
        value=payload.value,
        reason=payload.reason,
        user_id=payload.user_id,
    )
    db.add(row)
    await db.flush()

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="risk_blacklist",
        action="add_entry",
        target_id=row.id,
        changes={
            "entry_type": payload.entry_type,
            "value": payload.value,
            "reason": payload.reason,
        },
        severity="critical",
    )
    await db.commit()
    return {
        "id": row.id,
        "entry_type": row.entry_type,
        "value": row.value,
        "reason": row.reason,
        "user_id": row.user_id,
        "created_at": row.created_at,
    }


@router.delete("/blacklist/{entry_id}", status_code=status.HTTP_200_OK)
async def remove_from_blacklist(
    entry_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.scalar(
        select(RiskBlacklist).where(RiskBlacklist.id == entry_id, RiskBlacklist.deleted_at.is_(None))
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BLACKLIST_ENTRY_NOT_FOUND")

    row.deleted_at = datetime.now(timezone.utc)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="risk_blacklist",
        action="remove_entry",
        target_id=entry_id,
        changes={},
    )
    await db.commit()
    return {"removed_id": entry_id}


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


# ============================================================================
# Module 5 — Risk & Fraud dashboard, fraud alerts, underwriting queue
# ============================================================================


@router.get("/dashboard")
async def risk_dashboard(
    current_admin: AdminUser = Depends(RequirePermission("read_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    alerts_by_severity = (
        await db.execute(
            text(
                """
                SELECT severity, COUNT(*) AS cnt
                FROM fraud_alerts
                WHERE status = 'open'
                GROUP BY severity
                """
            )
        )
    ).mappings().all()
    review_by_status = (
        await db.execute(
            text(
                """
                SELECT status, COUNT(*) AS cnt
                FROM manual_review_queue
                GROUP BY status
                """
            )
        )
    ).mappings().all()
    avg_resolution_hours = await db.scalar(
        text(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0)
            FROM fraud_alerts
            WHERE resolved_at IS NOT NULL AND created_at >= NOW() - INTERVAL '30 days'
            """
        )
    )
    blacklist_total = int(
        await db.scalar(
            select(func.count(RiskBlacklist.id)).where(RiskBlacklist.deleted_at.is_(None))
        )
        or 0
    )
    overdue_sla = int(
        await db.scalar(
            text(
                """
                SELECT COUNT(*) FROM manual_review_queue
                WHERE status IN ('pending', 'in_review') AND sla_deadline IS NOT NULL AND sla_deadline < NOW()
                """
            )
        )
        or 0
    )

    return {
        "open_alerts_by_severity": {row["severity"]: int(row["cnt"]) for row in alerts_by_severity},
        "review_queue_by_status": {row["status"]: int(row["cnt"]) for row in review_by_status},
        "avg_resolution_hours_30d": round(float(avg_resolution_hours), 1) if avg_resolution_hours else None,
        "blacklist_total": blacklist_total,
        "review_queue_overdue_sla": overdue_sla,
    }


@router.get("/fraud-alerts")
async def list_fraud_alerts(
    status_filter: Optional[str] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("read_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        where_clauses.append("fa.status = :status_filter")
        params["status_filter"] = status_filter
    if severity:
        where_clauses.append("fa.severity = :severity")
        params["severity"] = severity
    if alert_type:
        where_clauses.append("fa.alert_type = :alert_type")
        params["alert_type"] = alert_type
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT fa.id, fa.uuid, fa.user_id, fa.order_id, fa.payment_id, fa.alert_type,
                       fa.severity, fa.source, fa.rule_code, fa.description, fa.status,
                       fa.investigated_by, fa.resolved_at, fa.action_taken, fa.created_at,
                       u.first_name, u.last_name, u.phone
                FROM fraud_alerts fa
                LEFT JOIN users u ON u.id = fa.user_id
                {where_sql}
                ORDER BY
                    CASE fa.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    fa.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    total = int(
        await db.scalar(
            text(f"SELECT COUNT(*) FROM fraud_alerts fa {where_sql}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r["id"],
                "uuid": str(r["uuid"]),
                "user_id": r["user_id"],
                "user_name": " ".join(filter(None, [r["first_name"], r["last_name"]])) or None,
                "user_phone": r["phone"],
                "order_id": r["order_id"],
                "payment_id": r["payment_id"],
                "alert_type": r["alert_type"],
                "severity": r["severity"],
                "source": r["source"],
                "rule_code": r["rule_code"],
                "description": r["description"],
                "status": r["status"],
                "investigated_by": r["investigated_by"],
                "resolved_at": _iso(r["resolved_at"]),
                "action_taken": r["action_taken"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/fraud-alerts/{alert_id}")
async def get_fraud_alert(
    alert_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT fa.*, u.first_name, u.last_name, u.phone, u.risk_band, u.credit_limit
                FROM fraud_alerts fa
                LEFT JOIN users u ON u.id = fa.user_id
                WHERE fa.id = :alert_id
                """
            ),
            {"alert_id": alert_id},
        )
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FRAUD_ALERT_NOT_FOUND")

    return {
        "id": row["id"],
        "uuid": str(row["uuid"]),
        "user_id": row["user_id"],
        "user_name": " ".join(filter(None, [row["first_name"], row["last_name"]])) or None,
        "user_phone": row["phone"],
        "user_risk_band": row["risk_band"],
        "user_credit_limit": float(row["credit_limit"]) if row["credit_limit"] is not None else None,
        "order_id": row["order_id"],
        "payment_id": row["payment_id"],
        "alert_type": row["alert_type"],
        "severity": row["severity"],
        "source": row["source"],
        "rule_code": row["rule_code"],
        "description": row["description"],
        "evidence": row["evidence"],
        "status": row["status"],
        "investigated_by": row["investigated_by"],
        "resolved_at": _iso(row["resolved_at"]),
        "resolution_note": row["resolution_note"],
        "action_taken": row["action_taken"],
        "created_at": _iso(row["created_at"]),
    }


class FraudAlertDecisionRequest(BaseModel):
    status: Literal["investigating", "resolved_genuine", "resolved_fraud", "false_positive"]
    resolution_note: Optional[str] = Field(default=None, max_length=1000)
    action_taken: Optional[str] = Field(default=None, max_length=50)


@router.post("/fraud-alerts/{alert_id}/decision")
async def decide_fraud_alert(
    alert_id: int,
    payload: FraudAlertDecisionRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id FROM fraud_alerts WHERE id = :id"), {"id": alert_id})
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FRAUD_ALERT_NOT_FOUND")

    resolved_now = payload.status in ("resolved_genuine", "resolved_fraud", "false_positive")
    await db.execute(
        text(
            """
            UPDATE fraud_alerts
            SET status = :status,
                investigated_by = :investigated_by,
                resolution_note = COALESCE(:resolution_note, resolution_note),
                action_taken = COALESCE(:action_taken, action_taken),
                resolved_at = CASE WHEN :resolved_now THEN NOW() ELSE resolved_at END
            WHERE id = :id
            """
        ),
        {
            "status": payload.status,
            "investigated_by": current_admin.id,
            "resolution_note": payload.resolution_note,
            "action_taken": payload.action_taken,
            "resolved_now": resolved_now,
            "id": alert_id,
        },
    )

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="fraud_alerts",
        action="decision",
        target_id=alert_id,
        changes={"status": payload.status, "action_taken": payload.action_taken},
    )
    await db.commit()
    return {"id": alert_id, "status": payload.status}


@router.get("/underwriting-queue")
async def list_underwriting_queue(
    status_filter: Optional[str] = None,
    priority: Optional[int] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("read_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        where_clauses.append("mrq.status = :status_filter")
        params["status_filter"] = status_filter
    if priority is not None:
        where_clauses.append("mrq.priority = :priority")
        params["priority"] = priority
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT mrq.id, mrq.uuid, mrq.entity_type, mrq.entity_id, mrq.queue_type,
                       mrq.priority, mrq.assigned_to, mrq.status, mrq.sla_deadline,
                       mrq.created_at, mrq.updated_at,
                       au.email AS assigned_to_email,
                       u.first_name, u.last_name, u.phone
                FROM manual_review_queue mrq
                LEFT JOIN admin_users au ON au.id = mrq.assigned_to
                LEFT JOIN users u ON u.id = mrq.entity_id AND mrq.entity_type = 'user'
                {where_sql}
                ORDER BY mrq.priority ASC, mrq.created_at ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    total = int(
        await db.scalar(
            text(f"SELECT COUNT(*) FROM manual_review_queue mrq {where_sql}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r["id"],
                "uuid": str(r["uuid"]),
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "entity_name": " ".join(filter(None, [r["first_name"], r["last_name"]])) or None,
                "entity_phone": r["phone"],
                "queue_type": r["queue_type"],
                "priority": r["priority"],
                "assigned_to": r["assigned_to"],
                "assigned_to_email": r["assigned_to_email"],
                "status": r["status"],
                "sla_deadline": _iso(r["sla_deadline"]),
                "sla_breached": bool(r["sla_deadline"] and r["status"] in ("pending", "in_review") and r["sla_deadline"] < datetime.now(timezone.utc).replace(tzinfo=None)),
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r["updated_at"]),
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/underwriting-queue/{item_id}")
async def get_underwriting_item(
    item_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                SELECT mrq.*, au.email AS assigned_to_email
                FROM manual_review_queue mrq
                LEFT JOIN admin_users au ON au.id = mrq.assigned_to
                WHERE mrq.id = :item_id
                """
            ),
            {"item_id": item_id},
        )
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="REVIEW_ITEM_NOT_FOUND")

    user_context = None
    bank_analysis = None
    if row["entity_type"] == "user":
        user_row = (
            await db.execute(
                text(
                    """
                    SELECT id, first_name, last_name, phone, status, credit_limit,
                           available_credit, risk_band
                    FROM users WHERE id = :uid
                    """
                ),
                {"uid": row["entity_id"]},
            )
        ).mappings().one_or_none()
        if user_row:
            user_context = {
                "id": user_row["id"],
                "name": " ".join(filter(None, [user_row["first_name"], user_row["last_name"]])) or None,
                "phone": user_row["phone"],
                "status": user_row["status"],
                "credit_limit": float(user_row["credit_limit"] or 0),
                "available_credit": float(user_row["available_credit"] or 0),
                "risk_band": user_row["risk_band"],
            }
        bank_row = (
            await db.execute(
                text(
                    """
                    SELECT period_start, period_end, avg_balance, income_estimate,
                           expense_ratio, salary_detected, nsf_events, source
                    FROM bank_statement_analysis
                    WHERE user_id = :uid
                    ORDER BY period_start DESC
                    LIMIT 1
                    """
                ),
                {"uid": row["entity_id"]},
            )
        ).mappings().one_or_none()
        if bank_row:
            bank_analysis = {
                "period_start": _iso(bank_row["period_start"]),
                "period_end": _iso(bank_row["period_end"]),
                "avg_balance": float(bank_row["avg_balance"]) if bank_row["avg_balance"] is not None else None,
                "income_estimate": float(bank_row["income_estimate"]) if bank_row["income_estimate"] is not None else None,
                "expense_ratio": float(bank_row["expense_ratio"]) if bank_row["expense_ratio"] is not None else None,
                "salary_detected": bank_row["salary_detected"],
                "nsf_events": bank_row["nsf_events"],
                "source": bank_row["source"],
            }

    return {
        "id": row["id"],
        "uuid": str(row["uuid"]),
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "queue_type": row["queue_type"],
        "priority": row["priority"],
        "assigned_to": row["assigned_to"],
        "assigned_to_email": row["assigned_to_email"],
        "status": row["status"],
        "sla_deadline": _iso(row["sla_deadline"]),
        "notes": row["notes"],
        "resolved_at": _iso(row["resolved_at"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "user_context": user_context,
        "bank_statement_analysis": bank_analysis,
    }


class UnderwritingDecisionRequest(BaseModel):
    status: Literal["in_review", "resolved", "escalated"]
    notes: Optional[str] = Field(default=None, max_length=1000)
    assign_to_me: bool = False


@router.post("/underwriting-queue/{item_id}/decision")
async def decide_underwriting_item(
    item_id: int,
    payload: UnderwritingDecisionRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id FROM manual_review_queue WHERE id = :id"), {"id": item_id})
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="REVIEW_ITEM_NOT_FOUND")

    resolved_now = payload.status == "resolved"
    await db.execute(
        text(
            """
            UPDATE manual_review_queue
            SET status = :status,
                notes = COALESCE(:notes, notes),
                assigned_to = CASE WHEN :assign_to_me THEN :admin_id ELSE assigned_to END,
                resolved_at = CASE WHEN :resolved_now THEN NOW() ELSE resolved_at END,
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "status": payload.status,
            "notes": payload.notes,
            "assign_to_me": payload.assign_to_me,
            "admin_id": current_admin.id,
            "resolved_now": resolved_now,
            "id": item_id,
        },
    )

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="manual_review_queue",
        action="decision",
        target_id=item_id,
        changes={"status": payload.status},
    )
    await db.commit()
    return {"id": item_id, "status": payload.status}


@router.get("/credit-policy")
async def get_credit_policy(
    current_admin: AdminUser = Depends(RequirePermission("read_risk")),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    all_params = await get_system_parameters(current_admin=current_admin, db=db, redis=redis)
    return {
        "parameters": {k: v for k, v in all_params["parameters"].items() if k in CREDIT_POLICY_KEYS},
    }


class UpdateCreditPolicyRequest(BaseModel):
    parameters: dict = Field(..., min_length=1)


@router.put("/credit-policy")
async def update_credit_policy(
    payload: UpdateCreditPolicyRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_risk")),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    unknown = set(payload.parameters) - set(CREDIT_POLICY_KEYS)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown credit policy keys: {sorted(unknown)}",
        )
    result = await update_system_parameters(
        payload=UpdateParametersRequest(parameters=payload.parameters),
        request=request,
        current_admin=current_admin,
        db=db,
        redis=redis,
    )
    return result
