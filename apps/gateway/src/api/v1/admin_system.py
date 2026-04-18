"""Admin System Parameters Management — GAP-F from the production audit."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/system", tags=["Admin System"])

_PARAM_CACHE_KEY = "sk:admin:system:parameters"
_PARAM_CACHE_TTL = 300  # 5 minutes

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
}


@router.get("/parameters")
async def get_system_parameters(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    cached = await redis.get(_PARAM_CACHE_KEY)
    if cached:
        try:
            return {"parameters": json.loads(cached), "cached": True}
        except Exception:
            pass

    # Attempt to load from system_parameters table; fall back to defaults if missing.
    q = text("SELECT param_key, param_value FROM system_parameters WHERE deleted_at IS NULL")
    try:
        rows = (await db.execute(q)).mappings().all()
        db_params = {r["param_key"]: r["param_value"] for r in rows}
    except Exception:
        db_params = {}

    params = {**_DEFAULTS, **db_params}
    await redis.set(_PARAM_CACHE_KEY, json.dumps(params), _PARAM_CACHE_TTL)
    return {"parameters": params, "cached": False}


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

    q = text(
        """
        INSERT INTO system_parameters (param_key, param_value)
        VALUES (:key, :value)
        ON CONFLICT (param_key) DO UPDATE
        SET param_value = EXCLUDED.param_value, updated_at = NOW()
        """
    )
    try:
        for key, value in payload.parameters.items():
            await db.execute(q, {"key": key, "value": str(value)})
        await db.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"SYSTEM_PARAMS_TABLE_MISSING: {exc}",
        )

    # Invalidate cache
    await redis.delete(_PARAM_CACHE_KEY)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="system",
        action="update_parameters",
        target_id=None,
        changes=payload.parameters,
    )
    return {"updated": list(payload.parameters.keys()), "status": "ok"}
