"""Rate limiting for product-service endpoints, built on the shared-kernel limiter.

GAP-C Resolution: enforce per-user / per-IP extract rate limit independently
of the global gateway limit. On Redis failure the limiter degrades
gracefully -- it logs a warning and allows the request through so that a
dead Redis shard never blocks the entire extract pipeline (``fail_open=True``
below).

This module used to hand-roll a fixed-window (INCR + EXPIRE) counter. It now
delegates the actual limiting to ``sk_shared.rate_limit.SlidingWindowRateLimiter``
(a superset Redis ZSET-backed sliding-window-log algorithm shared across the
fleet), keeping only the product-service-specific bits: resolving the
per-user/per-IP identity and attaching a ``Retry-After`` header to the 429
response, which the shared ``enforce()`` helper does not do on its own.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from sk_shared.rate_limit import SlidingWindowRateLimiter
from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)

# Matches the key prefix this limiter has always used
# (``sk:ratelimit:extract:{identifier}``), so in-flight windows survive the
# migration to the shared implementation.
EXTRACT_RATE_LIMIT_KEY_PREFIX = "sk:ratelimit:extract"


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
    limiter = SlidingWindowRateLimiter(
        redis,
        key_prefix=EXTRACT_RATE_LIMIT_KEY_PREFIX,
        fail_open=True,
    )

    allowed = await limiter.allow(identifier, limit, window_seconds)
    if not allowed:
        retry_after = window_seconds
        try:
            conn = redis.redis if hasattr(redis, "redis") else redis
            ttl = await conn.ttl(f"{EXTRACT_RATE_LIMIT_KEY_PREFIX}:{identifier}")
            if ttl and ttl > 0:
                retry_after = ttl
        except Exception:
            # Retry-After is best-effort; fall back to the configured window.
            pass

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="EXTRACT_RATE_LIMIT_EXCEEDED",
            headers={"Retry-After": str(max(retry_after, 1))},
        )
