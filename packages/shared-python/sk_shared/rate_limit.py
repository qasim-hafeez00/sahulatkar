"""Shared Redis-backed rate limiter for sk_shared.

This module consolidates four independently-built, subtly-inconsistent rate
limiters that had accumulated across the fleet:

- ``apps/gateway/src/core/rate_limit.py`` (``RateLimiter.check_rate_limit``) and
  ``apps/gateway/src/core/dependencies.py`` (``rate_limit_auth``): a Redis
  ZSET-backed **sliding-window log** keyed ``sk:rate_limit:{key}``. Used both
  as ASGI middleware (global/auth/user/admin limits) and as a FastAPI
  dependency. This is the most correct of the four algorithms — a true
  sliding window has no boundary where 2x the limit can slip through — so it
  is the algorithm this module generalizes.
- ``apps/ledger-service/src/core/rate_limit.py`` (``rate_limit_admin_writes``):
  a **fixed-window counter** (``INCR`` + ``EXPIRE``) keyed
  ``rate_limit:admin_write:{actor_id}``, hardcoded to 10/min for admin
  writes, falling back to client IP when no actor id is set.
- ``apps/payment-orchestrator/src/core/rate_limit.py`` (``RateLimiter.allow``):
  a **fixed-window counter** keyed ``sk:ratelimit:{key}:{window_bucket}``
  (bucket = ``int(time.time()) // window_seconds``), parameterized per-route
  via a ``rate_limit(limit, window)`` dependency factory. Also exposes
  ``current_count()``.
- ``apps/product-service/src/core/rate_limit.py`` (``enforce_extract_rate_limit``):
  a **fixed-window counter** keyed ``sk:ratelimit:extract:{identifier}``
  (per-user, falling back to per-IP) that *fails open* (logs and allows the
  request through) if Redis itself errors, so a dead Redis shard never blocks
  the extract pipeline.

Algorithm
---------
Sliding-window log: each allowed request is recorded as a member of a Redis
ZSET (score = request timestamp) at key ``{key_prefix}:{identity}``. Each
check trims members older than ``window_seconds``, counts what is left, and
-- if still under ``limit`` -- adds the new member and refreshes the key's
TTL. This is a superset of every fixed-window use case above (fixed-window is
just a sliding window sampled at bucket boundaries) with strictly better
correctness, at the cost of O(log N) Redis work per check instead of O(1).

Design so each existing call site can be expressed without behavior
regressions:

- ``key_prefix`` replaces each service's hardcoded prefix
  (``sk:rate_limit``, ``rate_limit:admin_write``, ``sk:ratelimit``, ...).
- ``limit`` / ``window_seconds`` are passed per call, exactly as today.
- ``fail_open`` (default ``False``) reproduces product-service's
  degrade-gracefully-on-Redis-error behavior when explicitly requested;
  gateway/ledger/payment-orchestrator do not currently swallow Redis errors,
  so they should leave it ``False``.

Example -- how gateway's existing usage would map onto this module
--------------------------------------------------------------------
::

    from sk_shared.rate_limit import SlidingWindowRateLimiter, rate_limit_dependency

    # gateway/src/core/rate_limit.py::rate_limit_middleware, global IP limit:
    #   limiter = RateLimiter(redis); await limiter.check_rate_limit(f"global:{ip_key}", 600, 60)
    limiter = SlidingWindowRateLimiter(redis, key_prefix="sk:rate_limit")
    is_allowed = await limiter.allow(f"global:{ip_key}", 600, 60)

    # gateway/src/core/dependencies.py::rate_limit_auth, as a FastAPI dependency:
    #   _: None = Depends(rate_limit_auth)
    rate_limit_auth = rate_limit_dependency(
        limit=10, window_seconds=60, key_prefix="sk:rate_limit:auth",
    )

    @router.post("/login")
    async def login(_: None = Depends(rate_limit_auth)):
        ...

Migrating gateway/ledger-service/payment-orchestrator/product-service's call
sites onto this module is a separate Phase 2 step (one service at a time) --
this module only builds and tests the shared implementation.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException, Request, status

from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)

DEFAULT_KEY_PREFIX = "sk:ratelimit"


class SlidingWindowRateLimiter:
    """Redis ZSET-backed sliding-window-log rate limiter.

    One instance can be shared across many call sites within a service; pass
    a distinct ``key_prefix`` per logical limiter (e.g. one for "auth
    attempts", one for "admin writes") so their Redis keys never collide, the
    same way each service previously namespaced its own hardcoded prefix.
    """

    def __init__(
        self,
        redis: RedisClient,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        fail_open: bool = False,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._fail_open = fail_open

    def _conn(self) -> Any:
        # Accept either a sk_shared.redis_client.RedisClient wrapper or a raw
        # redis.asyncio.Redis instance, mirroring the defensive
        # `hasattr(redis, "redis")` check already used in gateway's limiter.
        return self._redis.redis if hasattr(self._redis, "redis") else self._redis

    def _full_key(self, identity: str) -> str:
        return f"{self._key_prefix}:{identity}"

    async def allow(self, identity: str, limit: int, window_seconds: int) -> bool:
        """Return True if `identity` is within `limit` requests per `window_seconds`.

        Records the request (as a ZSET member) only when it is allowed, so a
        rejected request does not itself count against future windows.
        """
        key = self._full_key(identity)
        now = time.time()
        conn = self._conn()
        try:
            await conn.zremrangebyscore(key, 0, now - window_seconds)
            current_count = await conn.zcard(key)
            if current_count >= limit:
                return False

            member = f"{now}:{time.monotonic_ns()}"
            await conn.zadd(key, {member: now})
            await conn.expire(key, window_seconds)
            return True
        except Exception:
            logger.warning(
                "Rate limit check failed for key=%s (fail_open=%s)",
                key,
                self._fail_open,
                exc_info=True,
            )
            return self._fail_open

    # Back-compat alias matching gateway's original `RateLimiter.check_rate_limit(key, limit, window)`.
    async def check_rate_limit(self, key: str, limit: int, window: int) -> bool:
        return await self.allow(key, limit, window)

    async def current_count(self, identity: str, window_seconds: int) -> int:
        """Return the number of requests currently counted in the window (does not record a new one)."""
        key = self._full_key(identity)
        now = time.time()
        conn = self._conn()
        await conn.zremrangebyscore(key, 0, now - window_seconds)
        return await conn.zcard(key)

    async def enforce(
        self,
        identity: str,
        limit: int,
        window_seconds: int,
        *,
        detail: str = "RATE_LIMIT_EXCEEDED",
    ) -> None:
        """Raise HTTP 429 if `identity` has exceeded `limit` requests in `window_seconds`."""
        if not await self.allow(identity, limit, window_seconds):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


IdentityFn = Callable[[Request], str]
RedisResolverFn = Callable[[Request], RedisClient]


def _default_identity(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _default_get_redis(request: Request) -> RedisClient:
    return request.app.state.redis


def rate_limit_dependency(
    *,
    limit: int,
    window_seconds: int,
    key_prefix: str = DEFAULT_KEY_PREFIX,
    identity_fn: Optional[IdentityFn] = None,
    get_redis: Optional[RedisResolverFn] = None,
    fail_open: bool = False,
    detail: str = "RATE_LIMIT_EXCEEDED",
) -> Callable[[Request], Awaitable[None]]:
    """Build a FastAPI dependency enforcing `limit` requests per `window_seconds`.

    ``identity_fn(request) -> str`` extracts the per-caller identity (default:
    client IP -- pass something that reads ``request.state.actor_id`` /
    decodes a bearer token to reproduce ledger-service's or gateway's
    per-user/per-admin behavior). ``get_redis(request) -> RedisClient``
    extracts the shared Redis client (default: ``request.app.state.redis``,
    matching every existing service's `get_redis` dependency).

    Mirrors payment-orchestrator's ``rate_limit(limit, window)`` dependency
    factory, generalized with a configurable key prefix and identity
    extractor so it can also express gateway's and ledger-service's
    dependency-style call sites.
    """
    _identity_fn = identity_fn or _default_identity
    _get_redis = get_redis or _default_get_redis

    async def _dependency(request: Request) -> None:
        redis = _get_redis(request)
        limiter = SlidingWindowRateLimiter(redis, key_prefix=key_prefix, fail_open=fail_open)
        identity = _identity_fn(request)
        await limiter.enforce(identity, limit, window_seconds, detail=detail)

    return _dependency
