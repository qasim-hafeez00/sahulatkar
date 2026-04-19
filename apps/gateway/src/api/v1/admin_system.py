"""Admin System Parameters Management — GAP-F from the production audit."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
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
}


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

    # Invalidate cache by bumping version and writing to a new key namespace.
    new_version = await redis.incr(_PARAM_CACHE_VERSION_KEY)
    await redis.set(_cache_key_for_version(int(new_version)), json.dumps({**_DEFAULTS, **payload.parameters}), _PARAM_CACHE_TTL)

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
