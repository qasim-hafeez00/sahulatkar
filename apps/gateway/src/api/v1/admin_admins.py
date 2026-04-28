from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db
from src.core.audit import record_audit_event

router = APIRouter(prefix="/admin/admins", tags=["Admin Users Management"])

class AdminCreateRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)
    role_id: Optional[int] = None
    force_password_change: bool = True

@router.get("")
async def list_admins(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GW-GAP-17: Admin management list"""
    offset = (page - 1) * limit
    q = select(AdminUser).where(AdminUser.deleted_at.is_(None)).order_by(AdminUser.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    total = int(await db.scalar(select(func.count(AdminUser.id)).where(AdminUser.deleted_at.is_(None))) or 0)
    
    return {
        "items": [
            {
                "id": r.id,
                "email": r.email,
                "role_id": r.role_id,
                "mfa_enabled": r.mfa_enabled,
                "force_password_change": r.force_password_change,
                "locked_until": r.locked_until.isoformat() if r.locked_until else None,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }

@router.post("")
async def create_admin(
    payload: AdminCreateRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GW-GAP-17: Admin management create"""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    existing = await db.scalar(select(AdminUser).where(AdminUser.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EMAIL_ALREADY_EXISTS")
        
    new_admin = AdminUser(
        email=payload.email,
        password_hash=pwd_context.hash(payload.password),
        role_id=payload.role_id,
        force_password_change=payload.force_password_change,
        mfa_enabled=True,
    )
    db.add(new_admin)
    await db.flush()
    
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_management",
        action="admin_created",
        target_id=new_admin.id,
        changes={"email": payload.email, "role_id": payload.role_id},
    )
    await db.commit()
    return {"id": new_admin.id, "email": new_admin.email}
