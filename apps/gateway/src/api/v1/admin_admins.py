from __future__ import annotations

from sqlalchemy.orm import selectinload
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db
from src.services.rbac import RBACService

router = APIRouter(prefix="/admin/admins", tags=["Admin Users Management"])

# Admin creation lives exclusively in admin_auth.py's POST /admin/auth/admins,
# which resolves role by name against RBACService (matching how roles are
# actually authorized) and reuses the same password hashing as admin login.
# This router previously had its own divergent POST here — removed.


@router.get("")
async def list_admins(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GW-GAP-17: Admin management list"""
    offset = (page - 1) * limit
    q = (
        select(AdminUser)
        .options(selectinload(AdminUser.role))
        .where(AdminUser.deleted_at.is_(None))
        .order_by(AdminUser.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    total = int(await db.scalar(select(func.count(AdminUser.id)).where(AdminUser.deleted_at.is_(None))) or 0)

    return {
        "items": [
            {
                "id": r.id,
                "email": r.email,
                "role_id": r.role_id,
                "role_name": r.role.name if r.role else None,
                "mfa_enabled": r.mfa_enabled,
                "force_password_change": r.force_password_change,
                "locked_until": r.locked_until.isoformat() if r.locked_until else None,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/role-hierarchy")
async def role_hierarchy(
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
) -> dict:
    """Reference table of the 8 canonical roles and their permission sets."""
    return {
        "roles": [
            {"name": role, "permissions": RBACService.get_role_permissions(role)}
            for role in RBACService.CANONICAL_ROLES
        ]
    }
