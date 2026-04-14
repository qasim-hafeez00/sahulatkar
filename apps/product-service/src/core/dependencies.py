from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.database import SessionLocal
from sk_shared.redis_client import RedisClient


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


def get_current_user_id(request: Request) -> int | None:
    # Temporary placeholder until gateway-auth JWT middleware is wired in this service.
    header_value = request.headers.get("x-user-id")
    if header_value is None:
        return None
    try:
        return int(header_value)
    except ValueError:
        return None
