import hashlib
import uuid
import pyotp
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.auth import AdminUser
from src.core.kms import KMSProvider
from src.core.audit import record_audit_event
from src.schemas.auth import (
    AdminAuthResponse,
    AdminLoginRequest,
    AdminMfaSetupResponse,
    AdminMfaVerifyRequest,
)
from src.services.auth import AuthService
from src.services.rbac import RBACService
from src.core.dependencies import get_db, get_redis, get_current_admin, RequirePermission
from sk_shared.redis_client import RedisClient
from sk_shared.security import get_password_hash

router = APIRouter(prefix="/admin/auth", tags=["admin_auth"])

@router.post("/login", response_model=AdminAuthResponse)
async def admin_login(
    req: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    return await AuthService.admin_login(req, db, redis)

@router.post("/logout", status_code=204)
async def admin_logout(
    request: Request,
    admin = Depends(get_current_admin),
    redis: RedisClient = Depends(get_redis)
):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await redis.delete(f"sk:auth:admin_session:{token_hash}")
    return


@router.post("/mfa/setup", response_model=AdminMfaSetupResponse)
async def setup_mfa(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    secret = pyotp.random_base32()
    encrypted = KMSProvider().encrypt(secret)
    admin = await db.scalar(select(AdminUser).where(AdminUser.id == current_admin.id, AdminUser.deleted_at.is_(None)))
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ADMIN_NOT_FOUND")
    admin.mfa_secret_encrypted = encrypted
    admin.mfa_enabled = False
    await db.commit()
    qr_uri = pyotp.TOTP(secret).provisioning_uri(name=admin.email, issuer_name="SahulatKar")
    return AdminMfaSetupResponse(qr_uri=qr_uri, secret=secret)


@router.post("/mfa/verify")
async def verify_mfa(
    payload: AdminMfaVerifyRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    admin = await db.scalar(select(AdminUser).where(AdminUser.id == current_admin.id, AdminUser.deleted_at.is_(None)))
    if not admin or not admin.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA_NOT_SETUP")

    secret = KMSProvider().decrypt(admin.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(payload.totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_TOTP")

    admin.mfa_enabled = True
    await db.commit()
    return {"enabled": True}


# ── Admin RBAC Management (GAP-29) ───────────────────────────────────────────

class CreateAdminRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="analyst")


class AssignRoleRequest(BaseModel):
    role: Literal["super_admin", "risk_officer", "kyc_reviewer", "analyst", "support"] = "analyst"


@router.post("/admins", status_code=status.HTTP_201_CREATED)
async def create_admin(
    payload: CreateAdminRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.scalar(
        select(AdminUser).where(AdminUser.email == payload.email, AdminUser.deleted_at.is_(None))
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ADMIN_EMAIL_EXISTS")

    new_admin = AdminUser(
        uuid=uuid.uuid4(),
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        mfa_enabled=False,
    )
    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_rbac",
        action="create_admin",
        target_id=new_admin.id,
        changes={"email": payload.email, "role": payload.role},
    )
    return {
        "admin_id": new_admin.id,
        "email": new_admin.email,
        "mfa_enabled": new_admin.mfa_enabled,
        "created_at": new_admin.created_at,
    }


@router.put("/admins/{admin_id}/role")
async def assign_admin_role(
    admin_id: int,
    payload: AssignRoleRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    target = await db.scalar(
        select(AdminUser).where(AdminUser.id == admin_id, AdminUser.deleted_at.is_(None))
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ADMIN_NOT_FOUND")

    permissions = RBACService.get_role_permissions(payload.role)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_rbac",
        action="assign_role",
        target_id=admin_id,
        changes={"role": payload.role, "permissions": permissions},
    )
    return {
        "admin_id": admin_id,
        "role": payload.role,
        "permissions": permissions,
        "note": "Role applied to next login token. Existing sessions unaffected until expiry.",
    }


@router.get("/roles")
async def list_roles(
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
) -> dict:
    all_roles = ["super_admin", "risk_officer", "kyc_reviewer", "analyst", "support"]
    return {
        "roles": [
            {"name": role, "permissions": RBACService.get_role_permissions(role)}
            for role in all_roles
        ]
    }
