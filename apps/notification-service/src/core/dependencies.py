from typing import AsyncGenerator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.database import SessionLocal
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.services.aftership_client import AfterShipClient


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


def get_aftership_client(request: Request) -> AfterShipClient:
    return request.app.state.aftership_client


def get_current_user_id(x_user_id: str | None = Header(default=None)) -> int:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED")

    try:
        return int(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_USER_CONTEXT") from exc


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_INTERNAL")


def require_operations_manager(x_admin_role: str | None = Header(default=None)) -> None:
    if x_admin_role != "operations_manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_ADMIN")

def require_permissions(required_permissions: list[str]):
    def _check(x_admin_permissions: str | None = Header(default=None)):
        if not x_admin_permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_ADMIN_NO_PERMISSIONS")
        
        perms = [p.strip() for p in x_admin_permissions.split(",")]
        for rp in required_permissions:
            if rp in perms or "all_actions" in perms:
                return True
        
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN_ADMIN_INSUFFICIENT_PERMISSIONS")
    return _check
