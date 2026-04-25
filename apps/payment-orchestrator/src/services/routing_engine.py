"""
Gateway Routing Engine.

Selects the optimal payment gateway based on:
  1. User's explicit method choice (always honoured if gateway is healthy)
  2. Gateway health status (failure rate within sliding window)
  3. Configured priority order: Raast → JazzCash → SafePay

The engine uses Redis counters to track gateway failures in a rolling
window. Gateways exceeding GATEWAY_FAILURE_THRESHOLD within the window
are marked "degraded" and excluded from automatic routing.

This does NOT override explicit user selections — only used when the
platform needs to auto-select (e.g., billing sweep).
"""
from __future__ import annotations

import logging
import time

from sk_shared.redis_client import RedisClient

from src.config import settings

logger = logging.getLogger(__name__)

# Gateways in priority order (most preferred first for auto-selection).
# INR-03 fix: SafePay is the primary MVP gateway. Raast is Phase 3 (near-zero fee,
# T+0 settlement, but requires bank partner provisioning — do not auto-select until live).
_GATEWAY_PRIORITY = ["safepay", "jazzcash", "raast"]


class GatewayRoutingEngine:
    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def record_failure(self, gateway: str) -> None:
        """Record a gateway failure for health tracking."""
        key = self._failure_key(gateway)
        await self._redis.redis.incr(key)
        await self._redis.redis.expire(key, settings.GATEWAY_FAILURE_WINDOW_SECONDS * 2)
        count = int(await self._redis.redis.get(key) or 0)
        logger.warning(
            "Gateway failure recorded",
            extra={"gateway": gateway, "failure_count": count},
        )

    async def record_success(self, gateway: str) -> None:
        """Reset failure counter on success (partial: decrement by 1 to avoid penalising transient errors)."""
        key = self._failure_key(gateway)
        current = int(await self._redis.redis.get(key) or 0)
        if current > 0:
            await self._redis.redis.decr(key)

    async def is_degraded(self, gateway: str) -> bool:
        """Returns True if the gateway has too many recent failures."""
        key = self._failure_key(gateway)
        count = int(await self._redis.redis.get(key) or 0)
        return count >= settings.GATEWAY_FAILURE_THRESHOLD

    async def get_failure_count(self, gateway: str) -> int:
        key = self._failure_key(gateway)
        return int(await self._redis.redis.get(key) or 0)

    async def select_gateway(self, preferred: str | None = None) -> str:
        """
        Select the best available gateway.

        If `preferred` is specified and the gateway is healthy, it is returned.
        Otherwise falls through the priority list to find a healthy gateway.
        If all gateways are degraded, returns the least-degraded one (never fails hard).
        """
        if preferred is not None and not await self.is_degraded(preferred):
            return preferred

        # Try each gateway in priority order
        for gateway in _GATEWAY_PRIORITY:
            if not await self.is_degraded(gateway):
                logger.info("Auto-selected gateway", extra={"gateway": gateway, "preferred": preferred})
                return gateway

        # All degraded — return least-failed as last resort
        counts = {g: await self.get_failure_count(g) for g in _GATEWAY_PRIORITY}
        fallback = min(counts, key=counts.get)
        logger.error(
            "All gateways degraded — using fallback",
            extra={"fallback": fallback, "counts": counts},
        )
        return fallback

    async def get_health_summary(self) -> list[dict]:
        """Returns health summary for all gateways (admin visibility)."""
        summaries = []
        for gateway in _GATEWAY_PRIORITY:
            count = await self.get_failure_count(gateway)
            summaries.append({
                "gateway": gateway,
                "failure_count_window": count,
                "is_degraded": count >= settings.GATEWAY_FAILURE_THRESHOLD,
                "window_seconds": settings.GATEWAY_FAILURE_WINDOW_SECONDS,
            })
        return summaries

    def _failure_key(self, gateway: str) -> str:
        window = int(time.time()) // settings.GATEWAY_FAILURE_WINDOW_SECONDS
        return f"sk:gateway:failures:{gateway}:{window}"
