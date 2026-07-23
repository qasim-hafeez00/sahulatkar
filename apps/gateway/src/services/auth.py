import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from fastapi import HTTPException, status

logger = logging.getLogger("gateway")

def _utcnow():
    """Naive UTC datetime for TIMESTAMP WITHOUT TIME ZONE DB columns."""
    return datetime.utcnow()

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
            
        otp = "123456" if settings.ENVIRONMENT == "local" else generate_otp()
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

        logger.info(f"[DEV] OTP for {req.phone}: {otp}")

        # Format masked phone
        masked_phone = req.phone[:5] + "******" + req.phone[-2:] if len(req.phone) >= 11 else "******"
        dev_otp = otp if settings.ENVIRONMENT != "production" else None
        return RegisterInitiateResponse(otp_token=otp_token, masked_phone=masked_phone, dev_otp=dev_otp)

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
                    fail_user.locked_until = _utcnow() + timedelta(minutes=30)
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
            .values(revoked_at=_utcnow())
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
            expires_at=_utcnow() + timedelta(seconds=settings.JWT_REFRESH_TTL)
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
        if getattr(admin, "locked_until", None):
            locked_until = admin.locked_until if admin.locked_until.tzinfo else admin.locked_until.replace(tzinfo=timezone.utc)
            if locked_until > datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is temporarily locked")
            
        # Verify MFA Enforcement — issue a short-lived temp token (mirrors
        # FORCE_PASSWORD_CHANGE below) so the admin can actually reach
        # /mfa/setup and /mfa/verify without a real session existing yet.
        if getattr(settings, "REQUIRE_ADMIN_MFA", True) and not admin.mfa_enabled:
            temp_token = create_access_token(
                {"admin_id": admin.id, "scope": "mfa_setup", "token_type": "temp"},
                settings.JWT_PRIVATE_KEY,
                timedelta(minutes=15),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA_SETUP_REQUIRED",
                headers={"X-Temp-Token": temp_token, "X-Admin-Id": str(admin.id)},
            )

        # Verify TOTP
        if admin.mfa_enabled and admin.mfa_secret_encrypted:
            if not req.totp_code:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="TOTP_CODE_REQUIRED")
            
            # TASK-16 FIX: Add TOTP attempt lockout (max 5 failed attempts)
            totp_fail_key = f"sk:auth:admin_totp_fail:{admin.id}"
            fail_count_str = await redis.get(totp_fail_key)
            fail_count = int(fail_count_str) if fail_count_str else 0
            
            if fail_count >= 5:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="TOTP_LOCKED_TOO_MANY_ATTEMPTS",
                )
            
            from src.core.kms import KMSProvider
            kms = KMSProvider()
            decrypted_secret = kms.decrypt(admin.mfa_secret_encrypted)
            totp = pyotp.TOTP(decrypted_secret)
            if not totp.verify(req.totp_code):
                # Increment failure counter with 15-minute expiry
                await redis.incr(totp_fail_key)
                await redis.expire(totp_fail_key, 900)  # 15 minutes
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
            
            # Clear failure counter on successful verification
            await redis.delete(totp_fail_key)

                
        # MISS-02: Enforce force_password_change — return temp token, not a real session
        if getattr(admin, "force_password_change", False):
            temp_token = create_access_token(
                {"admin_id": admin.id, "scope": "change_password", "token_type": "temp"},
                settings.JWT_PRIVATE_KEY,
                timedelta(minutes=15),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="FORCE_PASSWORD_CHANGE",
                headers={"X-Temp-Token": temp_token, "X-Admin-Id": str(admin.id)},
            )

        # Fetch actual role and permissions
        from src.services.rbac import RBACService
        role_name = "admin"  # Default
        if admin.role:
            role_name = admin.role.name

        permissions = RBACService.get_role_permissions(role_name)
        
        acc_token = create_access_token(
            {"admin_id": admin.id, "role": role_name, "permissions": permissions, "token_type": "admin"},
            settings.JWT_PRIVATE_KEY,
            timedelta(seconds=settings.ADMIN_SESSION_TTL)
        )
        token_hash = hashlib.sha256(acc_token.encode()).hexdigest()

        # MISS: only 1 concurrent session per admin is permitted — kill every
        # previously-issued session for this admin before establishing the new one.
        if hasattr(redis, "redis"):
            old_hashes = await redis.redis.smembers(f"sk:auth:admin_sessions:{admin.id}")
            for old_hash in old_hashes:
                old_hash_str = old_hash.decode() if isinstance(old_hash, bytes) else old_hash
                await redis.delete(f"sk:auth:admin_session:{old_hash_str}")
            await redis.redis.delete(f"sk:auth:admin_sessions:{admin.id}")

        await redis.set(f"sk:auth:admin_session:{token_hash}", f"{admin.id}:{role_name}", settings.ADMIN_SESSION_TTL)

        if hasattr(redis, "redis"):
            await redis.redis.sadd(f"sk:auth:admin_sessions:{admin.id}", token_hash)
            await redis.redis.expire(f"sk:auth:admin_sessions:{admin.id}", settings.ADMIN_SESSION_TTL)

        # Mirror the single-session-per-admin policy into Postgres (admin_sessions)
        # so Module 12's session management UI has real, queryable rows — Redis
        # alone has no way to list/audit sessions across admins.
        await db.execute(
            text(
                "UPDATE admin_sessions SET revoked_at = NOW() WHERE admin_user_id = :admin_id AND revoked_at IS NULL"
            ),
            {"admin_id": admin.id},
        )
        await db.execute(
            text(
                """
                INSERT INTO admin_sessions (admin_user_id, token_hash, expires_at)
                VALUES (:admin_id, :token_hash, :expires_at)
                """
            ),
            {
                "admin_id": admin.id,
                "token_hash": token_hash,
                "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=settings.ADMIN_SESSION_TTL),
            },
        )
        await db.commit()

        return AdminAuthResponse(access_token=acc_token, token_type="bearer", admin_id=admin.id, role=role_name)

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
                    user.locked_until = _utcnow() + timedelta(minutes=30)
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
            await redis.delete(f"sk:auth:otp:{req.phone}:login")
        elif req.password:
            if not user.password_hash or not verify_password(req.password, user.password_hash):
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = _utcnow() + timedelta(minutes=30)
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
            .values(revoked_at=_utcnow())
        )

        # Generate tokens
        acc_token = create_access_token({"user_id": user.id}, settings.JWT_PRIVATE_KEY, timedelta(seconds=settings.JWT_ACCESS_TTL))
        ref_token = create_access_token({"user_id": user.id, "type": "refresh"}, settings.JWT_PRIVATE_KEY, timedelta(seconds=settings.JWT_REFRESH_TTL))
        
        session = UserSession(
            user_id=user.id,
            access_token_hash=hashlib.sha256(acc_token.encode()).hexdigest(),
            refresh_token_hash=hashlib.sha256(ref_token.encode()).hexdigest(),
            expires_at=_utcnow() + timedelta(seconds=settings.JWT_REFRESH_TTL)
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
    async def forgot_password(phone: str, db: AsyncSession, redis: RedisClient) -> dict:
        import json as _json
        result = await db.execute(select(User).where(User.phone == phone, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        masked = phone[:5] + "******" + phone[-2:] if len(phone) >= 11 else "******"
        if not user:
            # Return success-looking response to prevent user enumeration
            return {"masked_phone": masked, "reset_token": str(uuid.uuid4())}

        otp = "123456" if settings.ENVIRONMENT == "local" else generate_otp()
        reset_token = str(uuid.uuid4())
        hashed_otp = hash_otp(otp)

        await redis.set(f"sk:auth:otp:{phone}:reset", hashed_otp, settings.OTP_TTL)
        await redis.set(f"sk:auth:token:{reset_token}:reset", _json.dumps({"phone": phone, "user_id": user.id}), settings.OTP_TTL)

        if settings.NOTIFICATION_SMS_ENABLED:
            from sk_shared.notifications import NotificationClient
            notify_backend = redis.redis if hasattr(redis, "redis") else redis
            client = NotificationClient(notify_backend)
            try:
                await client.push_otp(phone, otp)
            except Exception:
                pass

        result = {"masked_phone": masked, "reset_token": reset_token}
        if settings.ENVIRONMENT != "production":
            result["dev_otp"] = otp
        return result

    @staticmethod
    async def reset_password(reset_token: str, otp_code: str, new_password: str, db: AsyncSession, redis: RedisClient) -> dict:
        import json as _json
        raw = await redis.get(f"sk:auth:token:{reset_token}:reset")
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RESET_TOKEN_EXPIRED")

        try:
            data = _json.loads(raw)
            phone = data["phone"]
            user_id = data["user_id"]
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RESET_TOKEN_INVALID")

        stored_hash = await redis.get(f"sk:auth:otp:{phone}:reset")
        if not stored_hash or stored_hash != hash_otp(otp_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OTP")

        result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

        user.password_hash = get_password_hash(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None

        # Revoke all existing sessions
        from sqlalchemy import update
        await db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )

        await redis.delete(f"sk:auth:otp:{phone}:reset")
        await redis.delete(f"sk:auth:token:{reset_token}:reset")
        await db.commit()
        return {"success": True}

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
            session.revoked_at = _utcnow()
            await db.commit()
