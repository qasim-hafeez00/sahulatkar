import pytest
from fastapi import HTTPException

import sk_shared.rate_limit as rate_limit_module
from sk_shared.rate_limit import SlidingWindowRateLimiter, rate_limit_dependency


class FakeRedis:
    """Minimal in-memory stand-in for the ZSET operations the limiter needs."""

    def __init__(self) -> None:
        self._zsets: dict[str, dict[str, float]] = {}
        self._ttls: dict[str, int] = {}

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> None:
        zset = self._zsets.get(key, {})
        for member in [m for m, s in zset.items() if min_score <= s <= max_score]:
            del zset[member]

    async def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self._zsets.setdefault(key, {}).update(mapping)

    async def expire(self, key: str, ttl: int) -> None:
        self._ttls[key] = ttl


class BrokenRedis:
    """Simulates a Redis connection that errors on every call."""

    async def zremrangebyscore(self, *args, **kwargs):
        raise ConnectionError("redis unavailable")


class StubClient:
    def __init__(self, host: str = "1.2.3.4") -> None:
        self.host = host


class StubAppState:
    def __init__(self, redis) -> None:
        self.redis = redis


class StubApp:
    def __init__(self, redis) -> None:
        self.state = StubAppState(redis)


class StubRequest:
    def __init__(self, redis, host: str = "1.2.3.4") -> None:
        self.client = StubClient(host)
        self.app = StubApp(redis)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def clock(monkeypatch):
    """Deterministic, controllable substitute for time.time() inside the module under test."""
    state = {"now": 1_700_000_000.0}
    monkeypatch.setattr(rate_limit_module.time, "time", lambda: state["now"])
    return state


async def test_allows_requests_under_the_limit(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    for _ in range(3):
        assert await limiter.allow("user-1", limit=3, window_seconds=60) is True


async def test_blocks_requests_at_the_limit(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    for _ in range(3):
        assert await limiter.allow("user-1", limit=3, window_seconds=60) is True

    assert await limiter.allow("user-1", limit=3, window_seconds=60) is False


async def test_window_reset_allows_again_after_expiry(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    for _ in range(2):
        assert await limiter.allow("user-1", limit=2, window_seconds=10) is True
    assert await limiter.allow("user-1", limit=2, window_seconds=10) is False

    clock["now"] += 11  # advance the clock past the window
    assert await limiter.allow("user-1", limit=2, window_seconds=10) is True


async def test_key_isolation_between_identities(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    for _ in range(2):
        assert await limiter.allow("user-1", limit=2, window_seconds=60) is True
    assert await limiter.allow("user-1", limit=2, window_seconds=60) is False

    # A different identity under the same prefix has its own independent budget.
    assert await limiter.allow("user-2", limit=2, window_seconds=60) is True


async def test_key_isolation_between_prefixes(fake_redis, clock):
    limiter_a = SlidingWindowRateLimiter(fake_redis, key_prefix="service-a")
    limiter_b = SlidingWindowRateLimiter(fake_redis, key_prefix="service-b")

    for _ in range(2):
        assert await limiter_a.allow("same-id", limit=2, window_seconds=60) is True
    assert await limiter_a.allow("same-id", limit=2, window_seconds=60) is False

    # Same identity, different key_prefix -> independent budget (no cross-talk).
    assert await limiter_b.allow("same-id", limit=2, window_seconds=60) is True


async def test_check_rate_limit_alias_matches_allow(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    assert await limiter.check_rate_limit("user-1", 1, 60) is True
    assert await limiter.check_rate_limit("user-1", 1, 60) is False


async def test_current_count_does_not_consume_budget(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    await limiter.allow("user-1", limit=5, window_seconds=60)
    await limiter.allow("user-1", limit=5, window_seconds=60)

    assert await limiter.current_count("user-1", window_seconds=60) == 2
    # Calling current_count again should not have added another member.
    assert await limiter.current_count("user-1", window_seconds=60) == 2


async def test_enforce_raises_http_429_when_exceeded(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    await limiter.allow("user-1", limit=1, window_seconds=60)

    with pytest.raises(HTTPException) as exc_info:
        await limiter.enforce("user-1", limit=1, window_seconds=60)
    assert exc_info.value.status_code == 429


async def test_enforce_passes_when_under_limit(fake_redis, clock):
    limiter = SlidingWindowRateLimiter(fake_redis, key_prefix="test")
    await limiter.enforce("user-1", limit=2, window_seconds=60)  # should not raise


async def test_fail_open_allows_through_on_redis_error(clock):
    limiter = SlidingWindowRateLimiter(BrokenRedis(), fail_open=True)
    assert await limiter.allow("user-1", limit=1, window_seconds=60) is True


async def test_fail_closed_by_default_on_redis_error(clock):
    limiter = SlidingWindowRateLimiter(BrokenRedis())
    assert await limiter.allow("user-1", limit=1, window_seconds=60) is False


async def test_rate_limit_dependency_allows_then_blocks(fake_redis, clock):
    dependency = rate_limit_dependency(limit=2, window_seconds=60, key_prefix="dep-test")
    request = StubRequest(fake_redis)

    await dependency(request)
    await dependency(request)
    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)
    assert exc_info.value.status_code == 429


async def test_rate_limit_dependency_isolates_different_client_ips(fake_redis, clock):
    dependency = rate_limit_dependency(limit=1, window_seconds=60, key_prefix="dep-test-ip")
    request_a = StubRequest(fake_redis, host="1.1.1.1")
    request_b = StubRequest(fake_redis, host="2.2.2.2")

    await dependency(request_a)
    with pytest.raises(HTTPException):
        await dependency(request_a)

    # A different client IP is unaffected.
    await dependency(request_b)
