"""
Redis-backed fixed-window rate limiter.

Usage:
    limiter = RateLimiter(redis_client)
    if not await limiter.allow(key="ip:1.2.3.4", limit=10, window_seconds=60):
        raise HTTPException(429, "RATE_LIMIT_EXCEEDED")
"""
import time

from sk_shared.redis_client import RedisClient


class RateLimiter:
    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def allow(self, *, key: str, limit: int, window_seconds: int) -> bool:
        """
        Returns True if the request is within the rate limit, False otherwise.
        Uses a fixed-window counter in Redis.
        """
        full_key = f"sk:ratelimit:{key}:{int(time.time()) // window_seconds}"
        current: bytes | None = await self._redis.get(full_key)
        count = int(current) if current else 0

        if count >= limit:
            return False

        pipe = self._redis.redis.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, window_seconds * 2)  # 2x window for safe expiry
        await pipe.execute()
        return True

    async def current_count(self, *, key: str, window_seconds: int) -> int:
        full_key = f"sk:ratelimit:{key}:{int(time.time()) // window_seconds}"
        current: bytes | None = await self._redis.get(full_key)
        return int(current) if current else 0
