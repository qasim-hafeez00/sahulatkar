from typing import AsyncGenerator, Optional
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sk_shared.database import SessionLocal
from sk_shared.redis_client import RedisClient
from sk_shared.security import decode_access_token
from sk_shared.models.auth import User, AdminUser
from src.config import settings

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
    payload: dict = Depends(get_current_user_token_payload),
    db: AsyncSession = Depends(get_db)
) -> User:
    user_id = payload.get("user_id")
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at == None))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.status in ["suspended", "blocked"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is blocked")
    return user

async def get_current_admin_token_payload(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    try:
        payload = decode_access_token(credentials.credentials, settings.JWT_PUBLIC_KEY)
        if "admin_id" not in payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload for admin")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate admin credentials")

async def get_current_admin(
    payload: dict = Depends(get_current_admin_token_payload),
    db: AsyncSession = Depends(get_db)
) -> AdminUser:
    admin_id = payload.get("admin_id")
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    return admin

class RequireRole:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, payload: dict = Depends(get_current_admin_token_payload)):
        role = payload.get("role")
        if role not in self.allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

class RequirePermission:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(self, payload: dict = Depends(get_current_admin_token_payload)):
        permissions = payload.get("permissions", [])
        if self.required_permission not in permissions and "all_actions" not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission")
