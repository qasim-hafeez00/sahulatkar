"""
FastAPI dependency injection for authentication, DB sessions, and Redis.
"""
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.database import SessionLocal
from sk_shared.models.auth import AdminUser, User
from sk_shared.redis_client import RedisClient
from sk_shared.security import decode_access_token

from src.config import settings
from src.core.security import constant_time_compare

security_scheme = HTTPBearer(auto_error=True)


# ── Database ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


# ── Redis ────────────────────────────────────────────────────────────────────

def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


# ── User Auth ────────────────────────────────────────────────────────────────

async def get_current_user_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    try:
        payload = decode_access_token(credentials.credentials, settings.JWT_PUBLIC_KEY)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_CREDENTIALS",
        ) from exc

    if "user_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_TOKEN_PAYLOAD",
        )
    return payload


async def get_current_user(
    payload: dict = Depends(get_current_user_token_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = payload.get("user_id")
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="USER_NOT_FOUND")
    if user.status in {"suspended", "blocked"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="USER_BLOCKED")
    return user


# ── Admin Auth ───────────────────────────────────────────────────────────────

async def get_current_admin_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    try:
        payload = decode_access_token(credentials.credentials, settings.JWT_PUBLIC_KEY)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_ADMIN_CREDENTIALS",
        ) from exc

    if "admin_id" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_ADMIN_TOKEN",
        )
    return payload


async def get_current_admin(
    payload: dict = Depends(get_current_admin_token_payload),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    admin_id = payload.get("admin_id")
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == admin_id, AdminUser.deleted_at.is_(None))
    )
    admin = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ADMIN_NOT_FOUND")
    return admin


class RequireRole:
    """Dependency that enforces admin role membership."""
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, payload: dict = Depends(get_current_admin_token_payload)) -> None:
        if payload.get("role") not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="INSUFFICIENT_PERMISSIONS",
            )


# ── Internal Service Auth ─────────────────────────────────────────────────────

async def require_internal_token(request: Request) -> None:
    """
    Validates the X-Internal-Token header for cross-service calls.
    Must be constant-time compared to prevent timing attacks.
    Rejected with 401 if missing or invalid.
    """
    token = request.headers.get("X-Internal-Token", "")
    if not settings.INTERNAL_API_TOKEN:
        if settings.ENVIRONMENT != "local":
            raise HTTPException(status_code=503, detail="INTERNAL_AUTH_NOT_CONFIGURED")
        import logging
        logging.getLogger(__name__).warning(
            "INTERNAL_API_TOKEN not configured — internal auth is DISABLED (allowed in local only)"
        )
        return
    if not constant_time_compare(token, settings.INTERNAL_API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INVALID_INTERNAL_TOKEN",
        )

# ── Rate Limiting ─────────────────────────────────────────────────────────────
#
# Migrated onto sk_shared.rate_limit.SlidingWindowRateLimiter (Phase 2 —
# adopting the shared-kernel rate limiter, replacing this service's bespoke
# fixed-window counter in src/core/rate_limit.py, now deleted). The sliding-
# window-log algorithm is strictly more correct than the old fixed-window
# counter (no boundary where 2x the limit can slip through). Key format
# ("ip:{host}") is preserved so existing callers of rate_limit(limit, window)
# don't need to change.

def rate_limit(limit: int, window: int):
    from sk_shared.rate_limit import rate_limit_dependency

    return rate_limit_dependency(
        limit=limit,
        window_seconds=window,
        key_prefix="sk:ratelimit",
        identity_fn=lambda request: f"ip:{request.client.host if request.client else 'unknown'}",
        get_redis=get_redis,
        fail_open=False,
        detail="RATE_LIMIT_EXCEEDED",
    )