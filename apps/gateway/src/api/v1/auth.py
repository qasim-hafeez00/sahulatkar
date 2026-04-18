from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from src.schemas.auth import (
    RegisterInitiateRequest, RegisterInitiateResponse,
    VerifyOtpRequest, AuthResponse, LoginRequest,
    TokenRefreshRequest, TokenRefreshResponse, CurrentUserResponse,
    ResendOtpRequest
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

@router.post("/otp/resend", response_model=RegisterInitiateResponse)
async def resend_otp(
    req: ResendOtpRequest,
    redis: RedisClient = Depends(get_redis)
):
    import json
    from fastapi import HTTPException
    import uuid
    from sk_shared.security import generate_otp, hash_otp
    from src.config import settings
    
    raw_payload = await redis.get(f"sk:auth:token:{req.otp_token}")
    if not raw_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP_EXPIRED")
    
    try:
        token_data = json.loads(raw_payload)
        phone = token_data.get("phone")
    except Exception:
        phone = raw_payload
        
    resend_count_key = f"sk:auth:otp_resend:{phone}"
    count = await redis.get(resend_count_key)
    if count and int(count) >= 3:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="TOO_MANY_RESENDS")
        
    await redis.incr(resend_count_key)
    if not count:
        await redis.expire(resend_count_key, 3600) # 1 hour
        
    otp = generate_otp()
    otp_token = str(uuid.uuid4())
    hashed_otp = hash_otp(otp)
    
    await redis.set(f"sk:auth:otp:{phone}:register", hashed_otp, settings.OTP_TTL)
    await redis.set(f"sk:auth:token:{otp_token}", raw_payload, settings.OTP_TTL)
    await redis.delete(f"sk:auth:token:{req.otp_token}")
    
    masked_phone = phone[:5] + "******" + phone[-2:] if len(phone) >= 11 else "******"
    return RegisterInitiateResponse(otp_token=otp_token, masked_phone=masked_phone)

@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: User = Depends(get_current_user)):
    credit_limit = getattr(user, 'credit_limit', 0.0)
    avail_credit = getattr(user, 'available_credit', 0.0)
    return CurrentUserResponse(
        user_id=user.id,
        uuid=user.uuid,
        phone=user.phone,
        kyc_status=user.status,
        credit_limit=credit_limit,
        available_credit=avail_credit,
        status=user.status
    )
