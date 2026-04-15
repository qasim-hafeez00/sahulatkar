from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from src.schemas.auth import (
    RegisterInitiateRequest, RegisterInitiateResponse,
    VerifyOtpRequest, AuthResponse, LoginRequest,
    TokenRefreshRequest, TokenRefreshResponse, CurrentUserResponse
)
from src.services.auth import AuthService
from src.core.dependencies import get_db, get_redis, get_current_user
from sk_shared.redis_client import RedisClient
from sk_shared.models.auth import User

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register/initiate", response_model=RegisterInitiateResponse)
async def register_initiate(
    req: RegisterInitiateRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    return await AuthService.initiate_registration(req, db, redis)

@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(
    req: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    return await AuthService.verify_otp(req, db, redis)

@router.post("/login", response_model=AuthResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    return await AuthService.login(req, db, redis)

@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh(
    req: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    return await AuthService.refresh_token(req, db, redis)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        await AuthService.logout(user.id, token, db, redis)
    return

@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return CurrentUserResponse(
        user_id=user.id,
        uuid=user.uuid,
        phone=user.phone,
        kyc_status=user.status,
        credit_limit=1000.0,
        available_credit=1000.0,
        status=user.status
    )
