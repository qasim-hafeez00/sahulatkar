import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.auth import (
    RegisterInitiateRequest, RegisterInitiateResponse,
    VerifyOtpRequest, AuthResponse, LoginRequest,
    TokenRefreshRequest, TokenRefreshResponse, CurrentUserResponse,
    ResendOtpRequest,
)
from src.services.auth import AuthService
from src.core.dependencies import get_db, get_redis, get_current_user, rate_limit_auth
from sk_shared.redis_client import RedisClient
from sk_shared.models.auth import User, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register/initiate", response_model=RegisterInitiateResponse)
async def register_initiate(
    req: RegisterInitiateRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth)
):
    return await AuthService.initiate_registration(req, db, redis)


@router.post("/verify-otp", response_model=AuthResponse)
async def verify_otp(
    req: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth)
):
    return await AuthService.verify_otp(req, db, redis)


@router.post("/login", response_model=AuthResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth)
):
    return await AuthService.login(req, db, redis)


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh(
    req: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth)
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
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth)
):
    import json
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
        await redis.expire(resend_count_key, 3600)

    otp = generate_otp()
    otp_token = str(uuid.uuid4())
    hashed_otp = hash_otp(otp)

    await redis.set(f"sk:auth:otp:{phone}:register", hashed_otp, settings.OTP_TTL)
    await redis.set(f"sk:auth:token:{otp_token}", raw_payload, settings.OTP_TTL)
    await redis.delete(f"sk:auth:token:{req.otp_token}")

    if settings.NOTIFICATION_SMS_ENABLED:
        from src.core.http_client import InternalServiceClient
        await InternalServiceClient.send_otp(
            phone=phone, otp_code=otp, purpose="registration", expires_in_seconds=settings.OTP_TTL,
        )

    masked_phone = phone[:5] + "******" + phone[-2:] if len(phone) >= 11 else "******"
    return RegisterInitiateResponse(otp_token=otp_token, masked_phone=masked_phone)


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(user: User = Depends(get_current_user)):
    credit_limit = getattr(user, "credit_limit", 0.0)
    avail_credit = getattr(user, "available_credit", 0.0)
    return CurrentUserResponse(
        user_id=user.id,
        uuid=user.uuid,
        phone=user.phone,
        kyc_status=user.status,
        credit_limit=credit_limit,
        available_credit=avail_credit,
        status=user.status,
    )


# ── MISS-01: Password Reset Flow ─────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+92[0-9]{10}$")


class ResetPasswordRequest(BaseModel):
    reset_token: str
    otp_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth),
) -> dict:
    return await AuthService.forgot_password(req.phone, db, redis)


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(rate_limit_auth),
) -> dict:
    return await AuthService.reset_password(req.reset_token, req.otp_code, req.new_password, db, redis)


# ── MISS-06: User Session Management ─────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    sessions = (
        await db.execute(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            ).order_by(UserSession.created_at.desc())
        )
    ).scalars().all()
    return {
        "user_id": user.id,
        "sessions": [
            {
                "id": s.id,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ],
    }


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    session = await db.scalar(
        select(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SESSION_NOT_FOUND")
    session.revoked_at = datetime.now(timezone.utc)
    await redis.delete(f"sk:auth:session:{session.access_token_hash}")
    await db.commit()
    return


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    current_token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        current_token = auth_header.split(" ")[1]
        hashlib.sha256(current_token.encode()).hexdigest()
    else:
        pass

    sessions = (
        await db.execute(
            select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        )
    ).scalars().all()
    for s in sessions:
        s.revoked_at = datetime.now(timezone.utc)
        await redis.delete(f"sk:auth:session:{s.access_token_hash}")

    await db.commit()
    return


# ── MISS-08: Device Token Registration ───────────────────────────────────────

class DeviceRegisterRequest(BaseModel):
    device_token: str = Field(..., min_length=10, max_length=512)
    platform: str = Field(..., pattern="^(ios|android)$")


@router.post("/devices/register", status_code=status.HTTP_201_CREATED)
async def register_device(
    req: DeviceRegisterRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from sk_shared.models.auth import UserDevice
    existing = await db.scalar(
        select(UserDevice).where(
            UserDevice.user_id == user.id,
            UserDevice.device_token == req.device_token,
            UserDevice.deleted_at.is_(None),
        )
    )
    if existing:
        existing.platform = req.platform
        existing.last_used_at = datetime.now(timezone.utc)
        existing.is_active = True
        await db.commit()
        return {"device_id": existing.id, "registered": True, "updated": True}

    device = UserDevice(
        user_id=user.id,
        device_token=req.device_token,
        platform=req.platform,
        is_active=True,
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return {"device_id": device.id, "registered": True, "updated": False}


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deregister_device(
    device_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sk_shared.models.auth import UserDevice
    device = await db.scalar(
        select(UserDevice).where(
            UserDevice.id == device_id,
            UserDevice.user_id == user.id,
            UserDevice.deleted_at.is_(None),
        )
    )
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DEVICE_NOT_FOUND")
    device.is_active = False
    device.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return


# ── MISS-18: User Account Deletion (GDPR/PECA) ───────────────────────────────

class AccountDeleteRequest(BaseModel):
    password: str = Field(..., min_length=1)


@router.delete("/account", status_code=status.HTTP_200_OK)
async def delete_account(
    req: AccountDeleteRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    from sk_shared.security import verify_password
    from sk_shared.models.payment import Loan

    # Verify password
    if not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_PASSWORD")

    # Block deletion if active loans exist
    active_loans = await db.scalar(
        select(Loan).where(
            Loan.user_id == user.id,
            Loan.status == "active",
            Loan.deleted_at.is_(None),
        )
    )
    if active_loans:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ACTIVE_LOANS_EXIST: Settle all outstanding loans before deleting account.",
        )

    # Revoke all sessions
    sessions = (
        await db.execute(
            select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        )
    ).scalars().all()
    for s in sessions:
        s.revoked_at = datetime.now(timezone.utc)
        await redis.delete(f"sk:auth:session:{s.access_token_hash}")

    # Anonymise PII and soft-delete (PECA compliance)
    anon_phone = f"+00000{user.id:08d}"
    user.phone = anon_phone
    user.first_name = "DELETED"
    user.last_name = "USER"
    user.password_hash = None
    user.deleted_at = datetime.now(timezone.utc)

    await db.commit()
    return {"success": True, "message": "Account deleted and PII anonymised."}
