import time
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sk_shared.redis_client import RedisClient
from sk_shared.security import decode_access_token
from src.config import settings

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
    # Global bypass for health check
    if request.url.path == "/health":
        return await call_next(request)
    
    # Bypass for tests unless we are specifically testing rate limits
    if settings.ENVIRONMENT == "test":
        if not request.headers.get("X-Test-Rate-Limit"):
            return await call_next(request)

    redis = request.app.state.redis
    limiter = RateLimiter(redis)
    
    ip = request.client.host
    path = request.url.path
    
    # Global limit: 100 requests per minute
    is_allowed = await limiter.check_rate_limit(f"global:{ip}", 100, 60)
    if not is_allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests. Please try again later."}
        )
        
    # Endpoint specific limits
    if "/auth/verify-otp" in path or "/auth/login" in path:
        # 10 attempts per minute
        if not await limiter.check_rate_limit(f"auth:{ip}", 10, 60):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many authentication attempts. Please wait a minute."}
            )

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        payload = {}
        try:
            payload = decode_access_token(token, settings.JWT_PUBLIC_KEY)
        except Exception:
            payload = {}

        user_id = payload.get("user_id")
        if user_id and not await limiter.check_rate_limit(f"user:{user_id}", 60, 60):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests for this account. Please retry shortly."},
            )

        admin_id = payload.get("admin_id")
        if admin_id and payload.get("token_type") == "admin":
            if not await limiter.check_rate_limit(f"admin:{admin_id}", settings.ADMIN_RATE_LIMIT_PER_MIN, 60):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Admin rate limit exceeded."},
                )

    response = await call_next(request)
    return response
