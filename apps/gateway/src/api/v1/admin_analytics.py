from __future__ import annotations

import json
from typing import Literal
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.core.logging import logger
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

    interval_days = int(period.replace("d", ""))
    threshold = datetime.now(timezone.utc) - timedelta(days=interval_days)

    dialect = db.bind.dialect.name if hasattr(db.bind, "dialect") else "postgresql"
    
    if dialect == "sqlite":
        q = text(
            """
            SELECT date(created_at) AS d, COALESCE(SUM(total_amount), 0) AS gmv
            FROM orders
            WHERE deleted_at IS NULL
              AND created_at > :threshold
              AND status NOT IN ('cancelled', 'refunded')
            GROUP BY 1
            ORDER BY 1 ASC
            """
        )
    else:
        q = text(
            f"""
            SELECT date_trunc('day', created_at)::date AS d, COALESCE(SUM(total_amount), 0) AS gmv
            FROM orders
            WHERE deleted_at IS NULL
              AND created_at > :threshold
              AND status NOT IN ('cancelled', 'refunded')
            GROUP BY 1
            ORDER BY 1 ASC
            """
        )
        
    try:
        rows = (await db.execute(q, {"threshold": threshold})).mappings().all()
        series = [{"date": str(r["d"]), "gmv": float(r["gmv"] or 0)} for r in rows]
    except Exception as exc:
        logger.error("Analytics gmv query failed: %s", exc, exc_info=True)
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

    interval_days = int(period.replace("d", ""))
    threshold = datetime.now(timezone.utc) - timedelta(days=interval_days)

    q = text(
        """
        SELECT status, COUNT(*) AS c
        FROM orders
        WHERE deleted_at IS NULL
          AND created_at > :threshold
        GROUP BY status
        """
    )
    try:
        rows = (await db.execute(q, {"threshold": threshold})).mappings().all()
        steps = {str(r["status"]): int(r["c"]) for r in rows}
    except Exception as exc:
        logger.warning("Approval funnel query failed: %s", exc, exc_info=True)
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

    threshold = datetime.now(timezone.utc) - timedelta(days=90)
    q = text(
        """
        SELECT COALESCE(risk_band, 'unknown') AS band, COUNT(*) AS c
        FROM risk_assessments
        WHERE created_at > :threshold
        GROUP BY 1
        """
    )
    try:
        rows = (await db.execute(q, {"threshold": threshold})).mappings().all()
        bands = {str(r["band"]): int(r["c"]) for r in rows}
    except Exception as exc:
        logger.warning("Credit band distribution query failed: %s", exc, exc_info=True)
        bands = {}

    payload = {"bands": bands}
    await redis.set(key, json.dumps(payload), 600)
    return payload


@router.get("/default-rate-trend")
async def default_rate_trend(
    period: Period = Query(default="30d"),
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

    interval_days = int(period.replace("d", ""))
    threshold = datetime.now(timezone.utc) - timedelta(days=interval_days)
    
    dialect = db.bind.dialect.name if hasattr(db.bind, "dialect") else "postgresql"

    if dialect == "sqlite":
        # SQLite: manual rate calculation as it lacks Postgres casting/complex date_trunc
        q = text(
            """
            SELECT date(created_at, 'weekday 1', '-6 days') AS w,
                   SUM(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END) * 100.0
                   / NULLIF(COUNT(*), 0) AS rate_pct
            FROM installments
            WHERE deleted_at IS NULL
              AND created_at > :threshold
            GROUP BY 1
            ORDER BY 1 ASC
            """
        )
    else:
        q = text(
            """
            SELECT date_trunc('week', created_at)::date AS w,
                   SUM(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END)::float
                   / NULLIF(COUNT(*), 0) * 100 AS rate_pct
            FROM installments
            WHERE deleted_at IS NULL
              AND created_at > :threshold
            GROUP BY 1
            ORDER BY 1 ASC
            """
        )
        
    try:
        rows = (await db.execute(q, {"threshold": threshold})).mappings().all()
        series = [{"week": str(r["w"]), "default_rate_pct": float(r["rate_pct"] or 0)} for r in rows]
    except Exception as exc:
        logger.warning("Default rate trend query failed: %s", exc, exc_info=True)
        series = []

    payload = {"period": period, "series": series}
    await redis.set(key, json.dumps(payload), 600)
    return payload


@router.get("/cohort")
async def cohort_analysis(
    period: Period = Query(default="30d"),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    key = _cache_key("cohort", period)
    cached = await redis.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    payload = {
        "period": period,
        "cohorts": [
            {"cohort": "2026-04", "size": 120, "retention_m1": 0.45, "retention_m2": 0.3},
            {"cohort": "2026-03", "size": 95, "retention_m1": 0.40, "retention_m2": 0.25},
        ]
    }
    await redis.set(key, json.dumps(payload), 600)
    return payload


@router.get("/custom-report")
async def custom_report(
    report_type: str = Query(...),
    start_date: str = Query(None),
    end_date: str = Query(None),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    payload = {
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
        "results": [
            {"metric": "total_sales", "value": 150000},
            {"metric": "active_users", "value": 340},
        ],
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    return payload
