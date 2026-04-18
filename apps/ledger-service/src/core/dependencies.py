from dataclasses import dataclass
import hmac
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from sk_shared.redis_client import RedisClient
from src.config import settings

@dataclass(slots=True)
class RequestContext:
    actor_type: str = "system"
    actor_id: str | None = None
    request_id: str | None = None
    actor_roles: tuple[str, ...] = ()


async def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


async def get_request_context(
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_actor_type: str | None = Header(default="system", alias="X-Actor-Type"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
    x_actor_roles: str | None = Header(default=None, alias="X-Actor-Roles"),
) -> RequestContext:
    roles = tuple(role.strip() for role in (x_actor_roles or "").split(",") if role.strip())
    return RequestContext(actor_type=x_actor_type or "system", actor_id=x_actor_id, request_id=x_request_id, actor_roles=roles)


def require_admin_role(required_roles: list[str]) -> Callable[..., RequestContext]:
    async def _dependency(context: RequestContext = Depends(get_request_context)) -> RequestContext:
        if context.actor_type != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ADMIN_ROLE_REQUIRED")

        if not set(context.actor_roles).intersection(required_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INSUFFICIENT_ADMIN_ROLE")
        return context

    return _dependency


async def require_internal_request(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if x_internal_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INTERNAL_TOKEN_REQUIRED")
    if not hmac.compare_digest(x_internal_token, settings.internal_api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_INTERNAL_TOKEN")
