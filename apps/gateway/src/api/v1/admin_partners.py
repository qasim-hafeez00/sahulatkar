from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/partners", tags=["Admin Partners"])

@router.get("/merchants")
async def list_merchants(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("read_partners")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GW-GAP-14: Merchant management panel stub"""
    # This assumes a merchant model doesn't fully exist yet or is external.
    # Return a stubbed list for the gap completion.
    return {
        "items": [],
        "pagination": {"page": page, "limit": limit, "total": 0},
        "status": "stub_implemented",
    }
