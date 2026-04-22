from fastapi import Depends, HTTPException, Request
from sk_shared.redis_client import RedisClient

from src.core.dependencies import get_redis

async def rate_limit_admin_writes(
    request: Request,
    redis: RedisClient = Depends(get_redis)
):
    """
    P3-05: Rate limiting on all admin write endpoints: 10 requests/minute per admin actor ID.
    If no actor ID is found in the state, falls back to IP.
    """
    actor_id = getattr(request.state, "actor_id", None)
    if not actor_id:
        actor_id = request.client.host if request.client else "unknown"

    key = f"rate_limit:admin_write:{actor_id}"
    
    # We use a simple sliding window or fixed window counter.
    # Fixed window is sufficient for this requirement.
    current_count = await redis.get(key)
    if current_count and int(current_count) >= 10:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 10 admin write requests per minute allowed."
        )
        
    # Increment and set TTL if it's the first request in the window
    await redis.incr(key)
    if not current_count:
        await redis.expire(key, 60)
        
    return True
