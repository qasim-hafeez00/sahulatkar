from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.auth import AdminLoginRequest, AdminAuthResponse
from src.services.auth import AuthService
from src.core.dependencies import get_db, get_redis, get_current_admin
from sk_shared.redis_client import RedisClient

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
