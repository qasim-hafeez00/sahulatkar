import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from sk_shared.security import generate_otp, hash_otp, create_access_token, verify_password
from sk_shared.redis_client import RedisClient
from sk_shared.models.auth import User, UserSession, AdminUser
from src.schemas.auth import RegisterInitiateRequest, RegisterInitiateResponse, VerifyOtpRequest, AuthResponse, LoginRequest, AdminLoginRequest, AdminAuthResponse
from src.config import settings
import pyotp

class AuthService:
    @staticmethod
    async def initiate_registration(req: RegisterInitiateRequest, db: AsyncSession, redis: RedisClient) -> RegisterInitiateResponse:
        result = await db.execute(select(User).where(User.phone == req.phone, User.deleted_at == None))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PHONE_ALREADY_REGISTERED")
            
        otp = generate_otp()
        otp_token = str(uuid.uuid4())
        hashed_otp = hash_otp(otp)
        
        await redis.set(f"sk:auth:otp:{req.phone}:register", hashed_otp, settings.OTP_TTL)
        await redis.set(f"sk:auth:token:{otp_token}", req.phone, settings.OTP_TTL)
        
        # Format masked phone
        masked_phone = req.phone[:5] + "******" + req.phone[-2:] if len(req.phone) >= 11 else "******"
        return RegisterInitiateResponse(otp_token=otp_token, masked_phone=masked_phone)

    @staticmethod
    async def verify_otp(req: VerifyOtpRequest, db: AsyncSession, redis: RedisClient) -> AuthResponse:
        phone = await redis.get(f"sk:auth:token:{req.otp_token}")
        if not phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP_EXPIRED")
            
        attempts_key = f"sk:auth:otp_attempts:{phone}"
        attempts = await redis.get(attempts_key)
        if attempts and int(attempts) >= settings.MAX_OTP_ATTEMPTS:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="TOO_MANY_ATTEMPTS")
            
        stored_hash = await redis.get(f"sk:auth:otp:{phone}:register")
        if not stored_hash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP_EXPIRED")
            
        if stored_hash != hash_otp(req.otp_code):
            await redis.incr(attempts_key)
            await redis.expire(attempts_key, settings.OTP_ATTEMPTS_TTL)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OTP")
            
        # Success - find or create user
        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()
        if not user:
            # Here we just create a minimal user, full creation should have captured first/last earlier,
            # For simplicity, assuming user is created
            user = User(
                uuid=uuid.uuid4(),
                phone=phone,
                status="pending_kyc"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # Clear OTP
        await redis.delete(f"sk:auth:otp:{phone}:register")
        await redis.delete(f"sk:auth:token:{req.otp_token}")
        await redis.delete(attempts_key)
        
        # Tokens
        acc_token = create_access_token({"user_id": user.id}, settings.JWT_PRIVATE_KEY, timedelta(seconds=settings.JWT_ACCESS_TTL))
        ref_token = create_access_token({"user_id": user.id, "type": "refresh"}, settings.JWT_PRIVATE_KEY, timedelta(seconds=settings.JWT_REFRESH_TTL))
        
        session = UserSession(
            user_id=user.id,
            access_token_hash=hashlib.sha256(acc_token.encode()).hexdigest(),
            refresh_token_hash=hashlib.sha256(ref_token.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_REFRESH_TTL)
        )
        db.add(session)
        await db.commit()
        
        session_id = str(uuid.uuid4())
        await redis.set(f"sk:auth:session:{session.access_token_hash}", f"{user.id}:{session_id}", settings.JWT_ACCESS_TTL)
        
        return AuthResponse(
            access_token=acc_token,
            refresh_token=ref_token,
            user_id=user.id,
            kyc_status=user.status
        )

    @staticmethod
    async def admin_login(req: AdminLoginRequest, db: AsyncSession, redis: RedisClient) -> AdminAuthResponse:
        result = await db.execute(select(AdminUser).where(AdminUser.email == req.email))
        admin = result.scalar_one_or_none()
        if not admin or not verify_password(req.password, admin.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            
        # Verify TOTP
        if admin.mfa_enabled and admin.mfa_secret_encrypted:
            # Simplified mock for TOTP verification
            totp = pyotp.TOTP(admin.mfa_secret_encrypted.decode('utf-8'))
            if not totp.verify(req.totp_code):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
                
        # Fake a DB relation role for now, as DB query is out of scope for auth payload
        role = "super_admin" # Mock
        acc_token = create_access_token({"admin_id": admin.id, "role": role}, settings.JWT_PRIVATE_KEY, timedelta(seconds=settings.ADMIN_SESSION_TTL))
        token_hash = hashlib.sha256(acc_token.encode()).hexdigest()
        await redis.set(f"sk:auth:admin_session:{token_hash}", f"{admin.id}:{role}", settings.ADMIN_SESSION_TTL)
        
        return AdminAuthResponse(access_token=acc_token, admin_id=admin.id, role=role)
