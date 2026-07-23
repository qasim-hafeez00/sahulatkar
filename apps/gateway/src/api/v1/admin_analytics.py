from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.core.logging import logger
from src.core.dependencies import RequirePermission, get_db, get_redis

router = APIRouter(prefix="/admin/analytics", tags=["Admin Analytics"])

Period = Literal["7d", "30d", "90d"]


def _cache_key(prefix: str, period: str) -> str:
    return f"sk:admin:analytics:{prefix}:{period}"


def _is_sqlite() -> bool:
    return settings.TESTING or settings.DB_DIALECT == "sqlite"


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
    threshold = (datetime.now(timezone.utc) - timedelta(days=interval_days)).replace(tzinfo=None)

    if _is_sqlite():
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
            """
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
    threshold = (datetime.now(timezone.utc) - timedelta(days=interval_days)).replace(tzinfo=None)

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

    threshold = (datetime.now(timezone.utc) - timedelta(days=90)).replace(tzinfo=None)
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
    threshold = (datetime.now(timezone.utc) - timedelta(days=interval_days)).replace(tzinfo=None)

    if _is_sqlite():
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

    if _is_sqlite():
        q = text(
            """
            SELECT strftime('%Y-%m', u.created_at) AS cohort,
                   COUNT(DISTINCT u.id) AS cohort_size,
                   COUNT(DISTINCT CASE
                       WHEN julianday(o.created_at) > julianday(u.created_at) + 30
                       THEN o.user_id END) AS m1_retained
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id AND o.deleted_at IS NULL
            WHERE u.deleted_at IS NULL
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 12
            """
        )
    else:
        q = text(
            """
            SELECT to_char(date_trunc('month', u.created_at), 'YYYY-MM') AS cohort,
                   COUNT(DISTINCT u.id) AS cohort_size,
                   COUNT(DISTINCT CASE
                       WHEN o.created_at > u.created_at + interval '30 days'
                       THEN o.user_id END) AS m1_retained
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id AND o.deleted_at IS NULL
            WHERE u.deleted_at IS NULL
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 12
            """
        )

    try:
        rows = (await db.execute(q)).mappings().all()
        cohorts = [
            {
                "cohort": str(r["cohort"]),
                "size": int(r["cohort_size"] or 0),
                "retention_m1": round(int(r["m1_retained"] or 0) / max(int(r["cohort_size"] or 1), 1), 4),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Cohort analysis query failed: %s", exc, exc_info=True)
        cohorts = []

    payload = {"period": period, "cohorts": cohorts}
    await redis.set(key, json.dumps(payload), 600)
    return payload


_CUSTOM_REPORT_QUERIES: dict[str, str] = {
    "revenue_by_period": """
        SELECT date_trunc_expr AS period,
               COALESCE(SUM(total_amount), 0) AS revenue,
               COUNT(*) AS order_count
        FROM orders
        WHERE deleted_at IS NULL
          AND status NOT IN ('cancelled', 'refunded')
          AND created_at BETWEEN :start_date AND :end_date
        GROUP BY 1
        ORDER BY 1
    """,
    "user_acquisition": """
        SELECT date_trunc_expr AS period,
               COUNT(*) AS new_users
        FROM users
        WHERE deleted_at IS NULL
          AND created_at BETWEEN :start_date AND :end_date
        GROUP BY 1
        ORDER BY 1
    """,
    "default_summary": """
        SELECT COUNT(*) AS overdue_count,
               COALESCE(SUM(total_amount - paid_amount), 0) AS overdue_amount
        FROM installments
        WHERE deleted_at IS NULL
          AND status = 'overdue'
          AND due_date BETWEEN :start_date AND :end_date
    """,
    "installment_collection": """
        SELECT date_trunc_expr AS period,
               COUNT(*) AS paid_count,
               COALESCE(SUM(paid_amount), 0) AS collected_amount
        FROM installments
        WHERE deleted_at IS NULL
          AND status = 'paid'
          AND paid_at BETWEEN :start_date AND :end_date
        GROUP BY 1
        ORDER BY 1
    """,
}


@router.get("/custom-report")
async def custom_report(
    report_type: str = Query(...),
    start_date: str = Query(None),
    end_date: str = Query(None),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    if report_type not in _CUSTOM_REPORT_QUERIES:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"UNKNOWN_REPORT_TYPE. Supported: {list(_CUSTOM_REPORT_QUERIES.keys())}",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        start = datetime.fromisoformat(start_date).replace(tzinfo=None) if start_date else now - timedelta(days=30)
        end = datetime.fromisoformat(end_date).replace(tzinfo=None) if end_date else now
    except ValueError:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_DATE_FORMAT: use ISO-8601")

    if _is_sqlite():
        trunc_expr = "date(created_at)"
    else:
        trunc_expr = "date_trunc('day', created_at)::date"

    raw_sql = _CUSTOM_REPORT_QUERIES[report_type].replace("date_trunc_expr", trunc_expr)

    try:
        rows = (await db.execute(text(raw_sql), {"start_date": start, "end_date": end})).mappings().all()
        results = [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("Custom report query failed: %s", exc, exc_info=True)
        results = []

    return {
        "report_type": report_type,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "results": results,
        "generated_at": now.isoformat(),
    }


@router.get("/export")
async def export_analytics(
    report_type: str = Query(..., description="One of: gmv, cohort, default_summary, installment_collection"),
    period: str = Query(default="30d"),
    format: str = Query(default="csv", pattern="^(csv)$"),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    interval_days = int(period.replace("d", "")) if period.endswith("d") else 30
    threshold = (datetime.now(timezone.utc) - timedelta(days=interval_days)).replace(tzinfo=None)

    if _is_sqlite():
        trunc_expr = "date(created_at)"
    else:
        trunc_expr = "date_trunc('day', created_at)::date"

    _export_queries: dict[str, tuple[str, list[str]]] = {
        "gmv": (
            f"""
            SELECT {trunc_expr} AS date, COALESCE(SUM(total_amount), 0) AS gmv
            FROM orders
            WHERE deleted_at IS NULL AND created_at > :threshold AND status NOT IN ('cancelled','refunded')
            GROUP BY 1 ORDER BY 1
            """,
            ["date", "gmv"],
        ),
        "cohort": (
            """
            SELECT strftime('%Y-%m', created_at) AS cohort, COUNT(*) AS new_users
            FROM users WHERE deleted_at IS NULL AND created_at > :threshold GROUP BY 1 ORDER BY 1
            """
            if _is_sqlite()
            else """
            SELECT to_char(date_trunc('month', created_at), 'YYYY-MM') AS cohort, COUNT(*) AS new_users
            FROM users WHERE deleted_at IS NULL AND created_at > :threshold GROUP BY 1 ORDER BY 1
            """,
            ["cohort", "new_users"],
        ),
        "default_summary": (
            f"""
            SELECT {trunc_expr} AS date,
                   SUM(CASE WHEN status='overdue' THEN 1 ELSE 0 END) AS overdue_count,
                   COALESCE(SUM(CASE WHEN status='overdue' THEN total_amount - paid_amount ELSE 0 END), 0) AS overdue_amount
            FROM installments WHERE deleted_at IS NULL AND created_at > :threshold GROUP BY 1 ORDER BY 1
            """,
            ["date", "overdue_count", "overdue_amount"],
        ),
        "installment_collection": (
            f"""
            SELECT {trunc_expr} AS date,
                   COUNT(*) AS paid_count,
                   COALESCE(SUM(paid_amount), 0) AS collected_amount
            FROM installments WHERE deleted_at IS NULL AND status='paid' AND paid_at > :threshold
            GROUP BY 1 ORDER BY 1
            """,
            ["date", "paid_count", "collected_amount"],
        ),
    }

    if report_type not in _export_queries:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"UNKNOWN_REPORT_TYPE. Supported: {list(_export_queries.keys())}",
        )

    sql, columns = _export_queries[report_type]
    try:
        rows = (await db.execute(text(sql), {"threshold": threshold})).mappings().all()
    except Exception as exc:
        logger.error("Export query failed: %s", exc, exc_info=True)
        rows = []

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})

    output.seek(0)
    filename = f"{report_type}_{period}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================================
# Module 9 — executive summary, geographic distribution
# ============================================================================

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}


@router.get("/executive-summary")
async def executive_summary(
    period: Period = Query(default="30d"),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    days = _PERIOD_DAYS[period]
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)
    prior_threshold = threshold - timedelta(days=days)

    async def _period_totals(start, end) -> dict:
        row = (
            await db.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS gmv,
                        COUNT(*) AS orders_count
                    FROM orders
                    WHERE deleted_at IS NULL AND status NOT IN ('cancelled', 'refunded')
                      AND created_at >= :start AND created_at < :end
                    """
                ),
                {"start": start, "end": end},
            )
        ).mappings().one()
        return {"gmv": float(row["gmv"] or 0), "orders_count": int(row["orders_count"] or 0)}

    current = await _period_totals(threshold, datetime.now(timezone.utc).replace(tzinfo=None))
    prior = await _period_totals(prior_threshold, threshold)

    new_users = await db.scalar(
        text("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL AND created_at >= :threshold"),
        {"threshold": threshold},
    )
    active_users = await db.scalar(
        text("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL AND status = 'active'"),
    )

    approved_apps = await db.scalar(
        text("SELECT COUNT(*) FROM credit_applications WHERE status = 'approved' AND created_at >= :threshold"),
        {"threshold": threshold},
    )
    decided_apps = await db.scalar(
        text("SELECT COUNT(*) FROM credit_applications WHERE status IN ('approved','rejected') AND created_at >= :threshold"),
        {"threshold": threshold},
    )
    approval_rate = round((approved_apps / decided_apps * 100), 2) if decided_apps else None

    overdue_installments = await db.scalar(
        text("SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status = 'overdue'"),
    )
    total_finished = await db.scalar(
        text("SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status IN ('overdue', 'paid')"),
    )
    default_rate = round((overdue_installments / total_finished * 100), 2) if total_finished else None

    def _growth_pct(current_val: float, prior_val: float):
        if prior_val == 0:
            return None
        return round((current_val - prior_val) / prior_val * 100, 1)

    return {
        "period": period,
        "gmv": current["gmv"],
        "gmv_growth_pct": _growth_pct(current["gmv"], prior["gmv"]),
        "orders_count": current["orders_count"],
        "orders_growth_pct": _growth_pct(current["orders_count"], prior["orders_count"]),
        "new_users": int(new_users or 0),
        "active_users": int(active_users or 0),
        "approval_rate_pct": approval_rate,
        "default_rate_pct": default_rate,
        "nps": None,
        "nps_note": "Not yet collected — no NPS capture mechanism exists in this codebase.",
    }


@router.get("/geographic")
async def geographic_distribution(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(u.province, 'Unknown') AS province,
                    COUNT(DISTINCT u.id) AS user_count,
                    COUNT(DISTINCT o.id) AS order_count,
                    COALESCE(SUM(o.total_amount) FILTER (WHERE o.status NOT IN ('cancelled', 'refunded')), 0) AS gmv
                FROM users u
                LEFT JOIN orders o ON o.user_id = u.id AND o.deleted_at IS NULL
                WHERE u.deleted_at IS NULL
                GROUP BY province
                ORDER BY user_count DESC
                """
            )
        )
    ).mappings().all()

    return {
        "provinces": [
            {
                "province": r["province"],
                "user_count": int(r["user_count"]),
                "order_count": int(r["order_count"]),
                "gmv": float(r["gmv"] or 0),
            }
            for r in rows
        ]
    }
