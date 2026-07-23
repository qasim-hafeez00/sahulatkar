"""Admin System Parameters Management — GAP-F from the production audit."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.admin import SystemParameter
from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/system", tags=["Admin System"])

_PARAM_CACHE_KEY = "sk:admin:system:parameters"
_PARAM_CACHE_VERSION_KEY = "sk:admin:system:parameters:version"
_PARAM_CACHE_TTL = 300  # 5 minutes


def _cache_key_for_version(version: int) -> str:
    return f"{_PARAM_CACHE_KEY}:v{version}"

# Default operational parameters (overridden by DB values when available)
_DEFAULTS: dict[str, Any] = {
    "max_credit_limit_pkr": 500_000,
    "min_order_amount_pkr": 5_000,
    "down_payment_pct": 25,
    "otp_ttl_seconds": 180,
    "max_otp_attempts": 3,
    "session_ttl_seconds": 900,
    "admin_session_ttl_seconds": 28800,
    "kyc_auto_approve_enabled": False,
    "notification_sms_enabled": True,
    "maintenance_mode": False,
    "require_admin_mfa": True,
    "admin_rate_limit_per_min": 30,
    "late_fee_rate_pkr_per_day": 50,
    "max_active_orders": 5,
    "wakalah_validity_days": 7,
    "murabaha_validity_days": 3,
    "profit_rate_3m": 2.5,
    "profit_rate_4m": 4.0,
    "profit_rate_6m": 7.0,
    "profit_rate_12m": 15.0,
    # Credit & underwriting policy (Module 5 — Risk & Fraud)
    "credit_min_score": 550,
    "credit_max_dti_ratio": 0.45,
    "credit_min_income_pkr": 30_000,
    "credit_min_account_age_days": 7,
    "credit_max_order_amount_new_user_pkr": 50_000,
    "credit_auto_approve_score_threshold": 720,
    "fraud_score_review_threshold": 0.5,
    "fraud_score_block_threshold": 0.85,
    "underwriting_sla_hours": 24,
    # Financial ops (Module 6)
    "gst_rate_pct": 18.0,
    "credit_loss_provision_rate_pct": 25.0,
    # Payment plan configuration (Module 13 — System Settings)
    "plan_3m_enabled": True,
    "plan_4m_enabled": True,
    "plan_6m_enabled": True,
    "plan_12m_enabled": True,
    "plan_3m_max_amount_pkr": 100_000,
    "plan_4m_max_amount_pkr": 150_000,
    "plan_6m_max_amount_pkr": 250_000,
    "plan_12m_max_amount_pkr": 500_000,
    # Fee structure configuration (Module 13 — System Settings)
    "processing_fee_pct": 1.5,
    "early_settlement_fee_pct": 2.0,
    "restructuring_fee_pkr": 1_000,
    "dishonored_payment_fee_pkr": 500,
}

PAYMENT_PLAN_KEYS: tuple[str, ...] = (
    "plan_3m_enabled", "plan_4m_enabled", "plan_6m_enabled", "plan_12m_enabled",
    "plan_3m_max_amount_pkr", "plan_4m_max_amount_pkr", "plan_6m_max_amount_pkr", "plan_12m_max_amount_pkr",
    "profit_rate_3m", "profit_rate_4m", "profit_rate_6m", "profit_rate_12m",
)

FEE_STRUCTURE_KEYS: tuple[str, ...] = (
    "processing_fee_pct", "early_settlement_fee_pct", "restructuring_fee_pkr",
    "dishonored_payment_fee_pkr", "late_fee_rate_pkr_per_day",
)

CREDIT_POLICY_KEYS: tuple[str, ...] = (
    "credit_min_score",
    "credit_max_dti_ratio",
    "credit_min_income_pkr",
    "credit_min_account_age_days",
    "credit_max_order_amount_new_user_pkr",
    "credit_auto_approve_score_threshold",
    "fraud_score_review_threshold",
    "fraud_score_block_threshold",
    "underwriting_sla_hours",
)


@router.get("/parameters")
async def get_system_parameters(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    version_raw = await redis.get(_PARAM_CACHE_VERSION_KEY)
    try:
        cache_version = int(version_raw or 1)
    except Exception:
        cache_version = 1
    cache_key = _cache_key_for_version(cache_version)

    cached = await redis.get(cache_key)
    if cached:
        try:
            return {"parameters": json.loads(cached), "cached": True, "cache_version": cache_version}
        except Exception:
            pass

    rows = (
        await db.execute(
            select(SystemParameter).where(SystemParameter.deleted_at.is_(None))
        )
    ).scalars().all()
    db_params = {r.param_key: r.param_value for r in rows}

    params = {**_DEFAULTS, **db_params}
    await redis.set(cache_key, json.dumps(params), _PARAM_CACHE_TTL)
    return {"parameters": params, "cached": False, "cache_version": cache_version}


class UpdateParametersRequest(BaseModel):
    parameters: dict[str, Any] = Field(..., min_length=1)


@router.put("/parameters")
async def update_system_parameters(
    payload: UpdateParametersRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    unknown_keys = set(payload.parameters) - set(_DEFAULTS)
    if unknown_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown parameter keys: {sorted(unknown_keys)}",
        )

    for key, value in payload.parameters.items():
        row = await db.scalar(
            select(SystemParameter).where(
                SystemParameter.param_key == key,
                SystemParameter.deleted_at.is_(None),
            )
        )
        if row is None:
            row = SystemParameter(param_key=key, param_value=str(value))
            db.add(row)
        else:
            row.param_value = str(value)

    # Invalidate cache by bumping version
    await redis.incr(_PARAM_CACHE_VERSION_KEY)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="system",
        action="update_parameters",
        target_id=None,
        changes=payload.parameters,
    )
    await db.commit()
    return {"updated": list(payload.parameters.keys()), "status": "ok"}


class SingleParameterUpdate(BaseModel):
    value: Any


@router.put("/parameters/{key}")
async def update_single_parameter(
    key: str,
    payload: SingleParameterUpdate,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """GW-GAP-02: Single parameter update endpoint."""
    if key not in _DEFAULTS:
        raise HTTPException(status_code=400, detail=f"UNKNOWN_PARAMETER: {key}")
    
    row = await db.scalar(
        select(SystemParameter).where(
            SystemParameter.param_key == key,
            SystemParameter.deleted_at.is_(None),
        )
    )
    if row is None:
        row = SystemParameter(param_key=key, param_value=str(payload.value))
        db.add(row)
    else:
        row.param_value = str(payload.value)

    await redis.incr(_PARAM_CACHE_VERSION_KEY)
    
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="system",
        action="update_parameter_single",
        target_id=None,
        changes={key: payload.value},
    )
    await db.commit()
    return {"updated": key, "status": "ok"}


# ============================================================================
# Module 13 — third-party integrations status/config view
# ============================================================================


@router.get("/integrations")
async def list_integrations(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT id, name, category, status, config, last_checked_at, updated_at
                FROM third_party_integrations
                ORDER BY category, name
                """
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "status": r["status"],
                "config": r["config"],
                "last_checked_at": r["last_checked_at"].isoformat() if r["last_checked_at"] else None,
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ]
    }


class UpdateIntegrationRequest(BaseModel):
    status: str = Field(..., pattern="^(not_configured|configured|healthy|degraded|failed)$")
    config: dict[str, Any] | None = None


@router.put("/integrations/{integration_id}")
async def update_integration(
    integration_id: int,
    payload: UpdateIntegrationRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id, name FROM third_party_integrations WHERE id = :id"), {"id": integration_id})
    row = existing.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INTEGRATION_NOT_FOUND")

    await db.execute(
        text(
            """
            UPDATE third_party_integrations
            SET status = :status,
                config = COALESCE(:config, config),
                last_checked_at = NOW(),
                updated_by = :updated_by,
                updated_at = NOW()
            WHERE id = :id
            """
        ),
        {
            "status": payload.status,
            "config": json.dumps(payload.config) if payload.config is not None else None,
            "updated_by": current_admin.id,
            "id": integration_id,
        },
    )
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="system",
        action="integration_status_updated",
        target_id=integration_id,
        changes={"name": row["name"], "status": payload.status},
    )
    await db.commit()
    return {"id": integration_id, "status": payload.status}


# ============================================================================
# GAP-15: System Health Dashboard
# ============================================================================

from datetime import datetime, timezone

@router.get("/health")
async def system_health(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    """GW-GAP-15: System health dashboard"""
    db_status = "up"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"

    redis_status = "up"
    try:
        if hasattr(redis, "redis"):
            await redis.redis.ping()
        else:
            redis_status = "unknown"
    except Exception:
        redis_status = "down"

    # Phase 4 — surface recorded metrics (latest value per metric_name) and
    # background job queue depth. system_health_metrics has no periodic
    # writer wired up yet, so this gracefully returns an empty list rather
    # than fabricating numbers until one exists.
    metric_rows = []
    try:
        metric_rows = (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT ON (metric_name) metric_name, metric_value, recorded_at
                    FROM system_health_metrics
                    ORDER BY metric_name, recorded_at DESC
                    """
                )
            )
        ).mappings().all()
    except Exception:
        metric_rows = []

    queue_depth = int(
        await db.scalar(text("SELECT COUNT(*) FROM background_jobs WHERE status IN ('queued', 'running')")) or 0
    )
    failed_jobs_24h = int(
        await db.scalar(
            text("SELECT COUNT(*) FROM background_jobs WHERE status = 'failed' AND enqueued_at >= NOW() - INTERVAL '24 hours'")
        )
        or 0
    )

    return {
        "status": "ok" if db_status == "up" and redis_status == "up" else "degraded",
        "components": {
            "database": {"status": db_status},
            "redis": {"status": redis_status},
        },
        "metrics": [
            {
                "metric_name": r["metric_name"],
                "value": float(r["metric_value"]),
                "recorded_at": r["recorded_at"].isoformat(),
            }
            for r in metric_rows
        ],
        "queue_depth": queue_depth,
        "failed_jobs_24h": failed_jobs_24h,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
