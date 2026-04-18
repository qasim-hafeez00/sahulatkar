import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from sk_shared.security import generate_otp, hash_otp, create_access_token, verify_password, decode_access_token, get_password_hash
from sk_shared.redis_client import RedisClient
from sk_shared.models.auth import User, UserSession, AdminUser
from src.schemas.auth import (
    RegisterInitiateRequest, RegisterInitiateResponse, VerifyOtpRequest, 
    AuthResponse, LoginRequest, AdminLoginRequest, AdminAuthResponse,
    TokenRefreshRequest, TokenRefreshResponse
)
from src.config import settings
import pyotp

class AuthService:
    @staticmethod
    async def initiate_registration(req: RegisterInitiateRequest, db: AsyncSession, redis: RedisClient) -> RegisterInitiateResponse:
        result = await db.execute(select(User).where(User.phone == req.phone, User.deleted_at.is_(None)))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PHONE_ALREADY_REGISTERED")
            
        otp = generate_otp()
        otp_token = str(uuid.uuid4())
        hashed_otp = hash_otp(otp)
        
        import json
        payload = {
            "phone": req.phone,
            "first_name": req.first_name,
            "last_name": req.last_name,
            "referral_code": req.referral_code,
            "password": req.password,
        }
        await redis.set(f"sk:auth:otp:{req.phone}:register", hashed_otp, settings.OTP_TTL)
        await redis.set(f"sk:auth:token:{otp_token}", json.dumps(payload), settings.OTP_TTL)
        
        # Format masked phone
        masked_phone = req.phone[:5] + "******" + req.phone[-2:] if len(req.phone) >= 11 else "******"
        return RegisterInitiateResponse(otp_token=otp_token, masked_phone=masked_phone)

    @staticmethod
    async def verify_otp(req: VerifyOtpRequest, db: AsyncSession, redis: RedisClient) -> AuthResponse:
        import json
        raw_payload = await redis.get(f"sk:auth:token:{req.otp_token}")
        if not raw_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP_EXPIRED")
        
        try:
            token_data = json.loads(raw_payload)
            phone = token_data.get("phone")
            first_name = token_data.get("first_name", "")
            last_name = token_data.get("last_name", "")
            referral_code = token_data.get("referral_code")
            password = token_data.get("password")
        except Exception:
            phone = raw_payload
            first_name = ""
            last_name = ""
            referral_code = None
            password = None
            
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

            fail_result = await db.execute(select(User).where(User.phone == phone))
            fail_user = fail_result.scalar_one_or_none()
            if fail_user:
                fail_user.failed_login_attempts = (fail_user.failed_login_attempts or 0) + 1
                if fail_user.failed_login_attempts >= 5:
                    fail_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                await db.commit()

            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OTP")

            
        # Success - find or create user
        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                uuid=uuid.uuid4(),
                phone=phone,
                first_name=first_name,
                last_name=last_name,
                status="pending_kyc"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        if referral_code and hasattr(user, "referral_code"):
            user.referral_code = referral_code
        if password:
            user.password_hash = get_password_hash(password)

        user.failed_login_attempts = 0
        user.locked_until = None
        
        from sqlalchemy import update
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        
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
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(AdminUser)
            .options(selectinload(AdminUser.role))
            .where(AdminUser.email == req.email, AdminUser.deleted_at.is_(None))
        )
        admin = result.scalar_one_or_none()
        
        if not admin or not verify_password(req.password, admin.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            
        # Check lockout
        if admin.locked_until:
            locked_until = admin.locked_until if admin.locked_until.tzinfo else admin.locked_until.replace(tzinfo=timezone.utc)
            if locked_until > datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is temporarily locked")
            
        # Verify MFA Enforcement
        if getattr(settings, "REQUIRE_ADMIN_MFA", True) and not admin.mfa_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA_SETUP_REQUIRED")

        # Verify TOTP
        if admin.mfa_enabled and admin.mfa_secret_encrypted:
            if not req.totp_code:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TOTP_CODE_REQUIRED")
            from src.core.kms import KMSProvider
            kms = KMSProvider()
            decrypted_secret = kms.decrypt(admin.mfa_secret_encrypted)
            totp = pyotp.TOTP(decrypted_secret)
            if not totp.verify(req.totp_code):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")

                
        # Fetch actual role and permissions
        from src.services.rbac import RBACService
        role_name = "admin"  # Default
        if admin.role:
            role_name = admin.role.name
            
        permissions = RBACService.get_role_permissions(role_name)
        
        acc_token = create_access_token(
            {"admin_id": admin.id, "role": role_name, "permissions": permissions}, 
            settings.JWT_PRIVATE_KEY, 
            timedelta(seconds=settings.ADMIN_SESSION_TTL)
        )
        token_hash = hashlib.sha256(acc_token.encode()).hexdigest()
        await redis.set(f"sk:auth:admin_session:{token_hash}", f"{admin.id}:{role_name}", settings.ADMIN_SESSION_TTL)
        
        if hasattr(redis, "redis"):
            await redis.redis.sadd(f"sk:auth:admin_sessions:{admin.id}", token_hash)
            await redis.redis.expire(f"sk:auth:admin_sessions:{admin.id}", settings.ADMIN_SESSION_TTL)
        
        return AdminAuthResponse(access_token=acc_token, admin_id=admin.id, role=role_name)

    @staticmethod
    async def login(req: LoginRequest, db: AsyncSession, redis: RedisClient) -> AuthResponse:
        # Initial implementation of phone/password login
        result = await db.execute(select(User).where(User.phone == req.phone, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            
        if user.locked_until:
            locked_until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
            if locked_until > datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is temporarily locked")

        if req.otp_code:
            stored_hash = await redis.get(f"sk:auth:otp:{req.phone}:login")
            if not stored_hash or stored_hash != hash_otp(req.otp_code):
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            await redis.delete(f"sk:auth:otp:{req.phone}:login")
        elif req.password:
            if not user.password_hash or not verify_password(req.password, user.password_hash):
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must provide password or otp_code")

        user.failed_login_attempts = 0
        user.locked_until = None
        
        await redis.delete(f"sk:auth:otp_attempts:{req.phone}")
        
        from sqlalchemy import update
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        
        # Generate tokens
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
        
        token_hash = session.access_token_hash
        await redis.set(f"sk:auth:session:{token_hash}", f"{user.id}", settings.JWT_ACCESS_TTL)
        
        return AuthResponse(
            access_token=acc_token,
            refresh_token=ref_token,
            user_id=user.id,
            kyc_status=user.status
        )

    @staticmethod
    async def refresh_token(req: TokenRefreshRequest, db: AsyncSession, redis: RedisClient) -> TokenRefreshResponse:
        try:
            payload = decode_access_token(req.refresh_token, settings.JWT_PUBLIC_KEY)
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
            user_id = payload.get("user_id")
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        # Check session in DB
        refresh_hash = hashlib.sha256(req.refresh_token.encode()).hexdigest()
        result = await db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == refresh_hash, 
                UserSession.revoked_at.is_(None)
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")
        expires_at = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")


        # Create new access token
        new_acc_token = create_access_token({"user_id": user_id}, settings.JWT_PRIVATE_KEY, timedelta(seconds=settings.JWT_ACCESS_TTL))
        
        # Update session access token hash
        new_acc_hash = hashlib.sha256(new_acc_token.encode()).hexdigest()
        session.access_token_hash = new_acc_hash
        await db.commit()
        
        # Update Redis
        await redis.set(f"sk:auth:session:{new_acc_hash}", f"{user_id}", settings.JWT_ACCESS_TTL)
        
        return TokenRefreshResponse(access_token=new_acc_token)

    @staticmethod
    async def logout(user_id: int, access_token: str, db: AsyncSession, redis: RedisClient):
        acc_hash = hashlib.sha256(access_token.encode()).hexdigest()
        
        # Revoke in Redis
        await redis.delete(f"sk:auth:session:{acc_hash}")
        
        # Revoke in DB
        result = await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id, 
                UserSession.access_token_hash == acc_hash
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()
