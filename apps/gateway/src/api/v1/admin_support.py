from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/support", tags=["Admin Support"])

@router.get("/tickets")
async def list_support_tickets(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    status: str | None = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_support")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GW-GAP-16: Support tickets panel stub"""
    # Assuming tickets are handled by an external service or not modeled yet
    return {
        "items": [],
        "pagination": {"page": page, "limit": limit, "total": 0},
        "status": "stub_implemented",
    }
