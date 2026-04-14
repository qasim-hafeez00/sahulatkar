from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser

from src.core.dependencies import get_current_admin, get_db

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


async def _fetch_scalar(db: AsyncSession, query: str) -> int:
    result = await db.execute(text(query))
    value = result.scalar_one_or_none()
    return int(value or 0)


@router.get("")
async def get_dashboard_summary(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    try:
        active_users = await _fetch_scalar(db, "SELECT COUNT(*) FROM users WHERE deleted_at IS NULL")
        total_orders = await _fetch_scalar(db, "SELECT COUNT(*) FROM orders WHERE deleted_at IS NULL")
        pending_installments = await _fetch_scalar(
            db,
            "SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status = 'pending'",
        )
        overdue_installments = await _fetch_scalar(
            db,
            "SELECT COUNT(*) FROM installments WHERE deleted_at IS NULL AND status = 'overdue'",
        )
    except Exception:
        active_users = 0
        total_orders = 0
        pending_installments = 0
        overdue_installments = 0

    return {
        "requested_by": {
            "admin_id": current_admin.id,
            "email": current_admin.email,
        },
        "kpis": {
            "gmv": {"value": float(Decimal("0.00")), "trend": "+0.0%", "status": "yellow"},
            "active_users": {"value": active_users, "trend": "+0.0%", "status": "yellow"},
            "approval_rate": {"value": 0.0, "trend": "+0.0%", "status": "yellow"},
            "default_rate": {"value": 0.0, "trend": "+0.0%", "status": "yellow"},
            "orders_today": {"value": total_orders, "trend": "+0.0%", "status": "yellow"},
            "payments_due": {"value": pending_installments, "trend": "+0.0%", "status": "yellow"},
            "overdue_amount": {"value": overdue_installments, "trend": "+0.0%", "status": "red"},
        },
        "action_items": [
            {
                "priority": "info",
                "type": "dashboard_contract_ready",
                "count": 1,
                "action_button": "open_modules",
            }
        ],
        "module_access": ["AD-01", "AD-02", "AD-03", "AD-04", "AD-05", "AD-06", "AD-07", "AD-08"],
    }
