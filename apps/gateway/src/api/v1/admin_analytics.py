from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])

Period = Literal["7d", "30d", "90d"]

_INTERVAL = {"7d": "7 days", "30d": "30 days", "90d": "90 days"}


def _cache_key(prefix: str, period: str) -> str:
    return f"sk:admin:analytics:{prefix}:{period}"


@router.get("/gmv-trend")
async def gmv_trend(
    period: Period = Query(default="30d"),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    key = _cache_key("gmv", period)
    cached = await redis.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    interval = _INTERVAL[period]
    q = text(
        f"""
        SELECT date_trunc('day', created_at)::date AS d, COALESCE(SUM(total_amount), 0) AS gmv
        FROM orders
        WHERE deleted_at IS NULL
          AND created_at > NOW() - INTERVAL '{interval}'
          AND status NOT IN ('cancelled', 'refunded')
        GROUP BY 1
        ORDER BY 1 ASC
        """
    )
    try:
        rows = (await db.execute(q)).mappings().all()
        series = [{"date": str(r["d"]), "gmv": float(r["gmv"] or 0)} for r in rows]
    except Exception:
        series = []

    payload = {"period": period, "series": series}
    await redis.set(key, json.dumps(payload), 600)
    return payload


@router.get("/approval-funnel")
async def approval_funnel(
    period: Period = Query(default="30d"),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    key = _cache_key("funnel", period)
    cached = await redis.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    interval = _INTERVAL[period]
    q = text(
        f"""
        SELECT status, COUNT(*) AS c
        FROM orders
        WHERE deleted_at IS NULL
          AND created_at > NOW() - INTERVAL '{interval}'
        GROUP BY status
        """
    )
    try:
        rows = (await db.execute(q)).mappings().all()
        steps = {str(r["status"]): int(r["c"]) for r in rows}
    except Exception:
        steps = {}

    payload = {"period": period, "steps": steps}
    await redis.set(key, json.dumps(payload), 600)
    return payload


@router.get("/credit-band-distribution")
async def credit_band_distribution(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    key = _cache_key("bands", "all")
    cached = await redis.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    q = text(
        """
        SELECT COALESCE(risk_band, 'unknown') AS band, COUNT(*) AS c
        FROM risk_assessments
        WHERE created_at > NOW() - INTERVAL '90 days'
        GROUP BY 1
        """
    )
    try:
        rows = (await db.execute(q)).mappings().all()
        bands = {str(r["band"]): int(r["c"]) for r in rows}
    except Exception:
        bands = {}

    payload = {"bands": bands}
    await redis.set(key, json.dumps(payload), 600)
    return payload


@router.get("/default-rate-trend")
async def default_rate_trend(
    period: Period = Query(default="90d"),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    key = _cache_key("default", period)
    cached = await redis.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    interval = _INTERVAL[period]
    q = text(
        f"""
        SELECT date_trunc('week', created_at)::date AS w,
               SUM(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END)::float
               / NULLIF(COUNT(*), 0) * 100 AS rate_pct
        FROM installments
        WHERE deleted_at IS NULL
          AND created_at > NOW() - INTERVAL '{interval}'
        GROUP BY 1
        ORDER BY 1 ASC
        """
    )
    try:
        rows = (await db.execute(q)).mappings().all()
        series = [{"week": str(r["w"]), "default_rate_pct": float(r["rate_pct"] or 0)} for r in rows]
    except Exception:
        series = []

    payload = {"period": period, "series": series}
    await redis.set(key, json.dumps(payload), 600)
    return payload
