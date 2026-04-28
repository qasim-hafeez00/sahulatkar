from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_current_admin, get_db, get_redis, RequirePermission
from src.core.logging import logger
from src.config import settings

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


async def _fetch_scalar(db: AsyncSession, query: str) -> float:
    try:
        result = await db.execute(text(query))
        value = result.scalar_one_or_none()
        return float(value or 0)
    except Exception as e:
        # M-04 FIX: Explicitly log DB errors instead of silent abandonment
        logger.error("Dashboard scalar fetch failed for query [%s]: %s", query, e)
        return 0.0


@router.get("")
async def get_dashboard_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> dict[str, object]:
    CACHE_KEY = "sk:admin:dashboard:kpis"
    
    # 1. Attempt Cache Retrieval
    cached_data = await redis.get(CACHE_KEY)
    if cached_data:
        try:
            return json.loads(cached_data)
        except Exception:
            pass

        # 2. Compute dynamic Live KPIs
    try:
        active_users = int(await _fetch_scalar(db, "SELECT COUNT(*) FROM users WHERE deleted_at IS NULL AND status = 'active'"))
        total_orders = int(await _fetch_scalar(db, "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL AND status NOT IN ('cancelled', 'refunded')"))
        
        gmv_raw = await _fetch_scalar(db, "SELECT SUM(total_amount) FROM orders WHERE deleted_at IS NULL AND status NOT IN ('cancelled', 'refunded')")
        
        pending_installments = int(await _fetch_scalar(db, "SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status = 'pending'"))
        overdue_installments = int(await _fetch_scalar(db, "SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status = 'overdue'"))
        overdue_amount_pkr = await _fetch_scalar(
            db,
            "SELECT COALESCE(SUM(total_amount), 0) FROM installments WHERE deleted_at IS NULL AND status = 'overdue'",
        )
        
        paid_installments = int(await _fetch_scalar(db, "SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status = 'paid'"))
        total_finished = overdue_installments + paid_installments
        
        # Portable threshold calculation
        threshold_30d = datetime.now(timezone.utc) - timedelta(days=30)
        
        approved_risk_result = await db.execute(
            text("SELECT COUNT(*) FROM risk_assessments WHERE decision = 'approved' AND created_at > :threshold"),
            {"threshold": threshold_30d}
        )
        approved_risk = int(approved_risk_result.scalar_one_or_none() or 0)
        
        total_risk_result = await db.execute(
            text("SELECT COUNT(*) FROM risk_assessments WHERE created_at > :threshold"),
            {"threshold": threshold_30d}
        )
        total_risk = int(total_risk_result.scalar_one_or_none() or 0)
        
        approval_rate = round((approved_risk / total_risk * 100), 2) if total_risk > 0 else 0.0
        
        default_rate = round((overdue_installments / total_finished * 100), 2) if total_finished > 0 else 0.0

    except Exception as e:
        logger.warning("Dashboard KPI query failed: %s", e, exc_info=True)
        active_users, total_orders, gmv_raw, pending_installments, overdue_installments, overdue_amount_pkr, default_rate, approval_rate = 0, 0, 0.0, 0, 0, 0.0, 0.0, 0.0

    response_payload = {
        "requested_by": {
            "admin_id": current_admin.id,
            "email": current_admin.email,
        },
        "kpis": {
            "gmv": {"value": gmv_raw, "trend": "+0.0%", "status": "green"},
            "active_users": {"value": active_users, "trend": "+0.0%", "status": "green"},
            "approval_rate": {"value": approval_rate, "trend": "+0.0%", "status": "yellow"},
            "default_rate": {"value": default_rate, "trend": "+0.0%", "status": "green" if default_rate < 5.0 else "red"},
            "orders_total": {"value": total_orders, "trend": "+0.0%", "status": "green"},
            "payments_due": {"value": pending_installments, "trend": "+0.0%", "status": "yellow"},
            "overdue_amount": {"value": overdue_amount_pkr, "trend": "+0.0%", "status": "red"},
        },
        "action_items": [
            {
                "priority": "info",
                "type": "dashboard_metrics_live",
                "count": 1,
                "action_button": "view_ledger",
            }
        ],
        "module_access": ["AD-01", "AD-02", "AD-03", "AD-04", "AD-05", "AD-06", "AD-07", "AD-08"],
        "cached": False
    }

    # 3. Cache Population (short TTL to keep operational metrics fresh)
    await redis.set(
        CACHE_KEY,
        json.dumps({**response_payload, "cached": True}),
        int(settings.ADMIN_DASHBOARD_CACHE_TTL),
    )

    return response_payload
