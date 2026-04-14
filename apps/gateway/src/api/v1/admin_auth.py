from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas.auth import AdminLoginRequest, AdminAuthResponse
from src.services.auth import AuthService
from src.core.dependencies import get_db, get_redis
from sk_shared.redis_client import RedisClient

router = APIRouter(prefix="/admin/auth", tags=["admin_auth"])

@router.post("/login", response_model=AdminAuthResponse)
async def admin_login(
    req: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    return await AuthService.admin_login(req, db, redis)
