import hashlib
from datetime import datetime, timezone
from typing import AsyncGenerator
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sk_shared.database import SessionLocal
from sk_shared.rate_limit import rate_limit_dependency
from sk_shared.redis_client import RedisClient
from sk_shared.security import decode_access_token
from sk_shared.models.auth import User, AdminUser
from src.config import settings

# Session inactivity-timeout ceiling per admin role (seconds). Shift-based
# roles get a longer window; everything else falls back to "default".
ADMIN_SESSION_TTL_BY_ROLE: dict[str, int] = {
    "cs_agent": 8 * 60 * 60,
    "default": 2 * 60 * 60,
}

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis

security_scheme = HTTPBearer()

async def get_current_user_token_payload(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    try:
        payload = decode_access_token(credentials.credentials, settings.JWT_PUBLIC_KEY)
        if "user_id" not in payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

async def get_current_user(
    request: Request,
    payload: dict = Depends(get_current_user_token_payload),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> User:
    user_id = payload.get("user_id")
    
    # Check session revocation in Redis/DB
    auth_header = request.headers.get("Authorization")
    if not auth_header:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    
    token = auth_header.split(" ")[1]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Fast check in Redis
    session_data = await redis.get(f"sk:auth:session:{token_hash}")
    if not session_data:
        # Fallback to DB check for safety
        from sk_shared.models.auth import UserSession
        result = await db.execute(select(UserSession).where(
            UserSession.access_token_hash == token_hash,
            UserSession.revoked_at.is_(None)
        ))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked or invalid")

    # Fetch user
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    
    # Check lockout
    if user.locked_until:
        locked_until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is locked")

    if user.status in ["suspended", "blocked"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is blocked")
    return user


async def get_current_admin_token_payload(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    try:
        payload = decode_access_token(credentials.credentials, settings.JWT_PUBLIC_KEY)
        if "admin_id" not in payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload for admin")
        if payload.get("token_type") != "admin":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload for admin")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate admin credentials")

async def get_current_admin(
    request: Request,
    payload: dict = Depends(get_current_admin_token_payload),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
) -> AdminUser:
    admin_id = payload.get("admin_id")
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
         
    token = auth_header.split(" ")[1]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    session_data = await redis.get(f"sk:auth:admin_session:{token_hash}")
    if not session_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin session revoked or expired")

    # MISS: inactivity timeout should be a sliding window (2h default, 8h for
    # shift-based roles like cs_agent), not a fixed session lifetime — refresh
    # the TTL on every authenticated request, capped by the role's ceiling.
    role = payload.get("role", "")
    ttl_ceiling = ADMIN_SESSION_TTL_BY_ROLE.get(role, ADMIN_SESSION_TTL_BY_ROLE["default"])
    await redis.expire(f"sk:auth:admin_session:{token_hash}", ttl_ceiling)

    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id, AdminUser.deleted_at.is_(None)))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found or deleted")
        
    return admin

class RequireRole:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, admin: AdminUser = Depends(get_current_admin), payload: dict = Depends(get_current_admin_token_payload)):
        role = payload.get("role")
        if role not in self.allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return admin

class RequirePermission:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(self, admin: AdminUser = Depends(get_current_admin), payload: dict = Depends(get_current_admin_token_payload)):
        permissions = payload.get("permissions", [])
        if self.required_permission not in permissions and "all_actions" not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission")
        return admin

async def get_admin_for_password_change(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> AdminUser:
    """Accepts both regular admin tokens and one-time temp tokens (FORCE_PASSWORD_CHANGE
    and MFA_SETUP_REQUIRED flows — an admin blocked at login by either of those has no
    real session yet, so change-password/mfa-setup/mfa-verify all accept this same
    short-lived, Redis-independent temp token instead)."""
    try:
        payload = decode_access_token(credentials.credentials, settings.JWT_PUBLIC_KEY)
        if "admin_id" not in payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    token_type = payload.get("token_type")
    admin_id = payload.get("admin_id")

    if token_type == "temp":
        if payload.get("scope") not in ("change_password", "mfa_setup"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token scope insufficient")
        # Temp tokens are not stored in Redis — validate by JWT signature alone
    elif token_type == "admin":
        token = credentials.credentials
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        session_data = await redis.get(f"sk:auth:admin_session:{token_hash}")
        if not session_data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin session revoked or expired")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id, AdminUser.deleted_at.is_(None)))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    return admin


# 10 requests / 60 seconds per IP, shared by /auth/register/initiate, /auth/verify-otp,
# /auth/login, /auth/refresh, /auth/otp/resend, /auth/forgot-password, /auth/reset-password.
# Preserves the bespoke dependency's original Redis key (`sk:rate_limit:auth:{ip}`) so this
# migration does not reset any in-flight rate-limit windows.
rate_limit_auth = rate_limit_dependency(
    limit=10,
    window_seconds=60,
    key_prefix="sk:rate_limit:auth",
    detail="Too many attempts. Try again later.",
)

