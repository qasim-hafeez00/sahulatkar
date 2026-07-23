"""
Tests for src/core/dependencies.py::rate_limit — migrated onto
sk_shared.rate_limit.SlidingWindowRateLimiter (Phase 2: adopting the
shared-kernel rate limiter). This replaces the service's old bespoke
fixed-window counter (formerly src/core/rate_limit.py, now deleted).

Exercises the real `rate_limit(limit, window)` dependency factory end to
end against fakeredis (via the `redis_mock` fixture), not a mocked-out
limiter, so a regression in the sk_shared wiring (wrong key prefix, wrong
identity function, etc.) would actually be caught here.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.dependencies import rate_limit

pytestmark = pytest.mark.asyncio


def _make_request(redis_mock, host: str = "1.2.3.4"):
    """Minimal stand-in for fastapi.Request — only .client.host and
    .app.state.redis are read by the rate_limit dependency."""
    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        app=SimpleNamespace(state=SimpleNamespace(redis=redis_mock)),
    )


async def test_rate_limit_allows_requests_under_the_limit(redis_mock):
    dependency = rate_limit(3, 60)
    request = _make_request(redis_mock)

    for _ in range(3):
        await dependency(request)  # must not raise


async def test_rate_limit_blocks_the_request_that_exceeds_the_limit(redis_mock):
    dependency = rate_limit(2, 60)
    request = _make_request(redis_mock)

    await dependency(request)
    await dependency(request)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "RATE_LIMIT_EXCEEDED"


async def test_rate_limit_isolates_different_client_ips(redis_mock):
    dependency = rate_limit(1, 60)
    request_a = _make_request(redis_mock, host="10.0.0.1")
    request_b = _make_request(redis_mock, host="10.0.0.2")

    await dependency(request_a)
    with pytest.raises(HTTPException):
        await dependency(request_a)

    # A different client IP has its own independent budget.
    await dependency(request_b)  # must not raise


async def test_rate_limit_budget_is_shared_across_dependency_instances_for_same_ip(redis_mock):
    """
    Documents pre-existing (preserved, not introduced by this migration)
    behavior: every `rate_limit(limit, window)` call site in src/api/v1/*.py
    keys off `ip:{host}` only, with no per-route component — so two
    independently-constructed dependencies for the same client IP draw from
    the *same* Redis budget. This was true of the old bespoke fixed-window
    RateLimiter too (same `key = f"ip:{host}"`, no route in the key). The
    sliding-window migration intentionally preserves this key shape rather
    than silently changing rate-limiting semantics as a side effect of the
    algorithm swap.
    """
    route_a_dependency = rate_limit(1, 60)  # e.g. vcn/void's rate_limit(10, 60)
    route_b_dependency = rate_limit(1, 60)  # e.g. vcn/issue's rate_limit(5, 60)
    request = _make_request(redis_mock, host="10.0.0.9")

    await route_a_dependency(request)  # consumes the one shared "slot" for this IP+window

    # A *different* dependency instance (simulating a different route) for
    # the same client IP is already blocked, because both key off
    # `ip:{host}` alone with no per-route distinction.
    with pytest.raises(HTTPException):
        await route_b_dependency(request)
