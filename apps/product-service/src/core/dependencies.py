from typing import AsyncGenerator
import hmac

from fastapi import Depends, Request, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.database import SessionLocal
from sk_shared.redis_client import RedisClient
from src.config import settings

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis

def require_service_token(
    internal_token: str = Header(None, alias="x-internal-service-token"),
) -> None:
    if not internal_token or not hmac.compare_digest(internal_token, settings.INTERNAL_SERVICE_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_SERVICE_TOKEN")


def get_current_user_id(
    request: Request,
    internal_token: str = Header(None, alias="x-internal-service-token"),
) -> int | None:
    """Zero-Trust Identity Resolution.
    
    Only trusts the x-user-id header if it is accompanied by a valid
    internal service token (HMAC-verified from the Gateway).
    """
    if not internal_token or not hmac.compare_digest(internal_token, settings.INTERNAL_SERVICE_TOKEN):
        # Prevent direct public access bypassing the Gateway.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="INVALID_SERVICE_TOKEN_OR_DIRECT_ACCESS"
        )
    
    header_value = request.headers.get("x-user-id")
    if not header_value:
        return None
        
    try:
        return int(header_value)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_USER_ID_FORMAT")


def require_user_id(
    user_id: int | None = Depends(get_current_user_id),
) -> int:
    """Enforce that a user ID must be present for this endpoint."""
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="USER_ID_REQUIRED")
    return user_id


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def get_client_ip(request: Request) -> str:
    """Resolve the best-effort client IP for rate limiting.

    Priority:
    1) x-real-ip (trusted ingress/header rewrite)
    2) first entry in x-forwarded-for
    3) request.client.host fallback
    """
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip

    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if first_hop:
            return first_hop

    if request.client and request.client.host:
        return request.client.host
    return "unknown"
