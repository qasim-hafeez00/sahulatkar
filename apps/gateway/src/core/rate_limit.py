import time
import hashlib
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
        current_time = time.time()
        window_key = f"sk:rate_limit:{key}"
        redis_instance = self.redis.redis if hasattr(self.redis, "redis") else self.redis

        await redis_instance.zremrangebyscore(window_key, 0, current_time - window)
        current_count = await redis_instance.zcard(window_key)
        if current_count >= limit:
            return False

        member = f"{current_time}:{time.monotonic_ns()}"
        await redis_instance.zadd(window_key, {member: current_time})
        await redis_instance.expire(window_key, window)
        return True

async def rate_limit_middleware(request: Request, call_next):
    # Global bypass for health check
    if request.url.path in {"/health", "/api/v1/health-check"}:
        return await call_next(request)
    
    # TASK-17 FIX: Bypass rate limiting for internal service endpoints
    # Internal endpoints use X-Internal-Token, not JWTs, so per-user limits don't apply
    if request.url.path.startswith("/api/v1/internal"):
        return await call_next(request)
    
    # Bypass for tests unless we are specifically testing rate limits
    if settings.ENVIRONMENT == "test":
        if not request.headers.get("X-Test-Rate-Limit"):
            return await call_next(request)

    redis = request.app.state.redis
    limiter = RateLimiter(redis)
    
    ip = request.client.host if request.client and request.client.host else "unknown"
    ip_key = hashlib.md5(ip.encode("utf-8")).hexdigest()[:16]
    path = request.url.path
    
    # Global limit: 100 requests per minute
    is_allowed = await limiter.check_rate_limit(f"global:{ip_key}", 100, 60)
    if not is_allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Too many requests. Please try again later."}
        )
        
    # Endpoint specific limits
    if "/auth/verify-otp" in path or "/auth/login" in path:
        # 10 attempts per minute
        if not await limiter.check_rate_limit(f"auth:{ip_key}", 10, 60):
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
            if not await limiter.check_rate_limit(f"admin:{admin_id}", int(settings.ADMIN_RATE_LIMIT_PER_MIN), 60):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Admin rate limit exceeded."},
                )

    response = await call_next(request)
    return response
