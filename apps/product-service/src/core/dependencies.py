from typing import AsyncGenerator

from fastapi import Request, HTTPException, status, Header
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
    if internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_SERVICE_TOKEN")


def get_current_user_id(
    request: Request,
    internal_token: str = Header(None, alias="x-internal-service-token"),
) -> int | None:
    if internal_token != settings.INTERNAL_SERVICE_TOKEN:
        # Gateway-driven Zero-Trust: If service token is absent or invalid, we refuse trust.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INVALID_SERVICE_TOKEN_OR_DIRECT_ACCESS")
    header_value = request.headers.get("x-user-id")
    if header_value is None:
        return None
    try:
        return int(header_value)
    except ValueError:
        return None
