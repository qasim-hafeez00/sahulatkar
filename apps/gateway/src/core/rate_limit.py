import time
from fastapi import Request, HTTPException, status
from sk_shared.redis_client import RedisClient

class RateLimiter:
    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def check_rate_limit(self, key: str, limit: int, window: int):
        """
        Check if the rate limit for a key is exceeded.
        :param key: Unique key for the rate limit (e.g., IP + endpoint)
        :param limit: Maximum number of requests allowed in the window
        :param window: Window size in seconds
        """
        # Simplified sliding window using Redis sorted sets or fixed window using INCR
        # We'll use fixed window for simplicity and performance in this sprint
        current_time = int(time.time())
        window_key = f"sk:rate_limit:{key}:{current_time // window}"
        
        count = await self.redis.incr(window_key)
        if count == 1:
            await self.redis.expire(window_key, window)
        
        if count > limit:
            return False
        return True

async def rate_limit_middleware(request: Request, call_next):
    # Skip rate limiting for health check
    if request.url.path == "/health":
        return await call_next(request)

    redis = request.app.state.redis
    limiter = RateLimiter(redis)
    
    ip = request.client.host
    path = request.url.path
    
    # Global limit: 100 requests per minute
    is_allowed = await limiter.check_rate_limit(f"global:{ip}", 100, 60)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )
        
    # Endpoint specific limits
    if "/auth/verify-otp" in path or "/auth/login" in path:
        # 10 attempts per minute
        if not await limiter.check_rate_limit(f"auth:{ip}", 10, 60):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please wait a minute."
            )

    response = await call_next(request)
    return response
