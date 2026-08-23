import hashlib
import uuid
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import text as _text
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.auth import AdminUser, Role
from src.core.kms import KMSProvider
from src.core.audit import record_audit_event
from src.schemas.auth import (
    AdminMfaSetupResponse,
    AdminMfaVerifyRequest,
)
from src.services.auth import AuthService
from src.services.rbac import RBACService
from src.core.dependencies import get_db, get_redis, get_current_admin, get_current_admin_token_payload, get_admin_for_password_change, RequirePermission
from sk_shared.redis_client import RedisClient
from sk_shared.security import get_password_hash
from src.schemas.admin_auth import AdminLoginRequest, AdminLoginResponse, AssignRoleRequest, CreateAdminRequest

# ADMIN SECURITY POLICY:
# 1. No refresh tokens permitted for admin accounts to minimize session longevity risks.
# 2. MFA is mandatory for all admin accounts (enforced via REQUIRE_ADMIN_MFA).
# 3. Role updates immediately invalidate ALL active sessions for that admin in Redis.
# 4. JWTs should have a short TTL (settings.ADMIN_TOKEN_EXPIRE_MINUTES).

router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])

class AdminMeResponse(BaseModel):
    admin_id: int
    email: str
    role: str | None = None
    mfa_enabled: bool
    permissions: list[str]


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    req: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    response = await AuthService.admin_login(req, db, redis)
    token_hash = hashlib.sha256(response.access_token.encode()).hexdigest()
    if hasattr(redis, "redis"):
        await redis.redis.sadd(f"sk:auth:admin_sessions:{response.admin_id}", token_hash)
        await redis.redis.expire(f"sk:auth:admin_sessions:{response.admin_id}", 28800)
    return response


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(
    current_admin: AdminUser = Depends(get_current_admin),
    payload: dict = Depends(get_current_admin_token_payload),
) -> AdminMeResponse:
    return AdminMeResponse(
        admin_id=current_admin.id,
        email=current_admin.email,
        role=payload.get("role"),
        mfa_enabled=current_admin.mfa_enabled,
        permissions=payload.get("permissions", []),
    )

@router.post("/logout", status_code=204)
async def admin_logout(
    request: Request,
    admin = Depends(get_current_admin),
    redis: RedisClient = Depends(get_redis)
):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await redis.delete(f"sk:auth:admin_session:{token_hash}")
    return


@router.post("/mfa/setup", response_model=AdminMfaSetupResponse)
async def setup_mfa(
    current_admin: AdminUser = Depends(get_admin_for_password_change),
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
    current_admin: AdminUser = Depends(get_admin_for_password_change),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    admin = await db.scalar(select(AdminUser).where(AdminUser.id == current_admin.id, AdminUser.deleted_at.is_(None)))
    if not admin or not admin.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA_NOT_SETUP")

    # TASK-16: Implement TOTP lockout (max 5 failed attempts)
    totp_fail_key = f"sk:auth:admin_totp_setup_fail:{admin.id}"
    fail_count_str = await redis.get(totp_fail_key)
    fail_count = int(fail_count_str) if fail_count_str else 0
    
    if fail_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="TOTP_LOCKED_TOO_MANY_ATTEMPTS",
        )

    secret = KMSProvider().decrypt(admin.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(payload.totp_code):
        await redis.incr(totp_fail_key)
        await redis.expire(totp_fail_key, 900)  # 15 minutes
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_TOTP")

    await redis.delete(totp_fail_key)
    admin.mfa_enabled = True
    await db.commit()
    return {"enabled": True}
# ── Admin RBAC Management (GAP-29) ───────────────────────────────────────────


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

    role_obj = await db.scalar(select(Role).where(Role.name == payload.role))
    
    new_admin = AdminUser(
        uuid=uuid.uuid4(),
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        mfa_enabled=False,
        role_id=role_obj.id if role_obj else None,
    )
    db.add(new_admin)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_rbac",
        action="create_admin",
        target_id=new_admin.id,
        changes={"email": payload.email, "role": payload.role},
    )
    await db.commit()
    await db.refresh(new_admin)
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

    role_obj = await db.scalar(select(Role).where(Role.name == payload.role))
    if role_obj:
        target.role_id = role_obj.id
        
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_rbac",
        action="assign_role",
        target_id=admin_id,
        changes={"role": payload.role, "permissions": permissions},
    )
    await db.commit()
    
    # Invalidate all existing sessions for this admin
    sessions_key = f"sk:auth:admin_sessions:{admin_id}"
    session_hashes = await redis.redis.smembers(sessions_key)
    for h in session_hashes:
        token_hash = h.decode() if isinstance(h, bytes) else str(h)
        await redis.delete(f"sk:auth:admin_session:{token_hash}")
    await redis.delete(sessions_key)

    return {
        "admin_id": admin_id,
        "role": payload.role,
        "permissions": permissions,
        "note": "Role applied to DB. Existing sessions invalidated successfully.",
    }


# ── MISS-02 / MISS-16: Admin Password Change ─────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=10, max_length=128)


@router.post("/change-password")
async def admin_change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_admin: AdminUser = Depends(get_admin_for_password_change),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MISS-16: Admin self-service password change.
    Also used to fulfil the FORCE_PASSWORD_CHANGE flow when a temp token is presented."""
    from sk_shared.security import verify_password
    from src.core.audit import record_audit_event

    admin = await db.scalar(select(AdminUser).where(AdminUser.id == current_admin.id, AdminUser.deleted_at.is_(None)))
    if not admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ADMIN_NOT_FOUND")

    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CURRENT_PASSWORD")

    admin.password_hash = get_password_hash(payload.new_password)
    admin.force_password_change = False

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=admin.id,
        module="admin_auth",
        action="password_changed",
        target_id=admin.id,
        changes={},
    )
    await db.commit()
    return {"success": True, "message": "Password updated successfully."}


# No local class definitions here; using src.schemas.admin_auth imports.
@router.get("/roles")
async def list_roles(
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
) -> dict:
    return {
        "roles": [
            {"name": role, "permissions": RBACService.get_role_permissions(role)}
            for role in RBACService.CANONICAL_ROLES
        ]
    }


# ============================================================================
# Module 12 — active session management, session policy
# ============================================================================

@router.get("/sessions")
async def list_admin_sessions(
    admin_id: int | None = None,
    active_only: bool = True,
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where_clauses = []
    params: dict = {}
    if admin_id is not None:
        where_clauses.append("s.admin_user_id = :admin_id")
        params["admin_id"] = admin_id
    if active_only:
        where_clauses.append("s.revoked_at IS NULL AND s.expires_at > NOW()")
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            _text(
                f"""
                SELECT s.id, s.admin_user_id, a.email, s.ip, s.device_info,
                       s.created_at, s.expires_at, s.revoked_at
                FROM admin_sessions s
                JOIN admin_users a ON a.id = s.admin_user_id
                {where_sql}
                ORDER BY s.created_at DESC
                LIMIT 200
                """
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": r["id"],
                "admin_id": r["admin_user_id"],
                "admin_email": r["email"],
                "ip": str(r["ip"]) if r["ip"] else None,
                "device_info": r["device_info"],
                "created_at": r["created_at"].isoformat(),
                "expires_at": r["expires_at"].isoformat(),
                "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
                "is_active": r["revoked_at"] is None,
            }
            for r in rows
        ]
    }


@router.post("/sessions/{session_id}/revoke")
async def revoke_admin_session(
    session_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    row = (
        await db.execute(
            _text("SELECT admin_user_id, token_hash, revoked_at FROM admin_sessions WHERE id = :id"),
            {"id": session_id},
        )
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SESSION_NOT_FOUND")
    if row["revoked_at"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SESSION_ALREADY_REVOKED")

    await db.execute(
        _text("UPDATE admin_sessions SET revoked_at = NOW() WHERE id = :id"), {"id": session_id}
    )
    await redis.delete(f"sk:auth:admin_session:{row['token_hash']}")
    if hasattr(redis, "redis"):
        await redis.redis.srem(f"sk:auth:admin_sessions:{row['admin_user_id']}", row["token_hash"])

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_rbac",
        action="session_revoked",
        target_id=session_id,
        changes={"target_admin_id": row["admin_user_id"]},
        severity="critical",
    )
    await db.commit()
    return {"session_id": session_id, "status": "revoked"}


class SessionPolicyRequest(BaseModel):
    role: str
    timeout_seconds: int = Field(..., gt=0, le=86400)


@router.put("/session-policy")
async def update_session_policy(
    payload: SessionPolicyRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_admins")),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    if payload.role not in RBACService.CANONICAL_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UNKNOWN_ROLE")

    from sk_shared.models.admin import SystemParameter

    param_key = f"admin_session_timeout_{payload.role}_seconds"
    row = await db.scalar(
        select(SystemParameter).where(SystemParameter.param_key == param_key, SystemParameter.deleted_at.is_(None))
    )
    if row is None:
        row = SystemParameter(param_key=param_key, param_value=str(payload.timeout_seconds))
        db.add(row)
    else:
        row.param_value = str(payload.timeout_seconds)

    await redis.incr("sk:admin:system:parameters:version")
    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_rbac",
        action="session_policy_updated",
        target_id=None,
        changes={"role": payload.role, "timeout_seconds": payload.timeout_seconds},
    )
    await db.commit()
    return {"role": payload.role, "timeout_seconds": payload.timeout_seconds}
