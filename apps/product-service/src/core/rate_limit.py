"""Redis-backed sliding window rate limiter for product-service endpoints.

GAP-C Resolution: enforce per-user / per-IP extract rate limit independently
of the global gateway limit.  On Redis failure the limiter degrades
gracefully — it logs a warning and allows the request through so that a
dead Redis shard never blocks the entire extract pipeline.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)


async def enforce_extract_rate_limit(
    redis: RedisClient,
    user_id: int | None,
    ip: str,
    limit: int = 10,
    window_seconds: int = 60,
) -> None:
    """Raise HTTP 429 if the caller has exceeded the extract rate limit.

    Uses a per-user key when user_id is available, falls back to IP.
    The limit applies to each identifier independently (not combined).

    Args:
        redis: Shared Redis client.
        user_id: Authenticated user ID (may be ``None`` for unauthenticated calls).
        ip: Request client IP address (fallback identifier).
        limit: Maximum allowed requests per *window_seconds* (default 10).
        window_seconds: Sliding-window duration in seconds (default 60).

    Raises:
        HTTPException: 429 with ``Retry-After`` header when limit is exceeded.
    """
    identifier = str(user_id) if user_id is not None else ip
    key = f"sk:ratelimit:extract:{identifier}"
    try:
        count = await redis.redis.incr(key)
        if count == 1:
            # First call in this window — set expiry
            await redis.redis.expire(key, window_seconds)
        if count > limit:
            retry_after = await redis.redis.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="EXTRACT_RATE_LIMIT_EXCEEDED",
                headers={"Retry-After": str(max(retry_after, 1))},
            )
    except HTTPException:
        raise
    except Exception as exc:
        # Never block on rate-limiter failure — degrade gracefully
        logger.warning("Rate-limit check failed, allowing through: %s", exc)
