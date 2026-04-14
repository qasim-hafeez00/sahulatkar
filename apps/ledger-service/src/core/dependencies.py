from dataclasses import dataclass

from fastapi import Header, HTTPException, Request, status

from sk_shared.redis_client import RedisClient

@dataclass(slots=True)
class RequestContext:
    actor_type: str = "system"
    actor_id: str | None = None
    request_id: str | None = None


async def get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


async def get_request_context(
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_actor_type: str | None = Header(default="system", alias="X-Actor-Type"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
) -> RequestContext:
    return RequestContext(actor_type=x_actor_type or "system", actor_id=x_actor_id, request_id=x_request_id)


async def require_internal_request(x_internal_token: str | None = Header(default=None, alias="X-Internal-Token")) -> None:
    if x_internal_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INTERNAL_TOKEN_REQUIRED")
