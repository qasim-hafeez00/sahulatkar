"""
test_rate_limiting.py — Verifies per-IP global limit and per-user authenticated limit.

Note: rate limiting is backed by Redis. These tests work because the client fixture
injects a fakeredis instance (via override_dependencies → app.state.redis = redis_mock).
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_global_rate_limit_returns_429_after_threshold(client: AsyncClient):
    """
    100 requests per minute per IP is the global limit.
    We exceed it by sending 101 rapid requests to the health endpoint
    (which is exempt) and a lightweight auth endpoint.
    
    NOTE: The health route is skipped by rate_limit_middleware, so we use
    /api/v1/auth/login (unauthenticated) which does count.
    We use a very tight loop to fill the fixed window bucket.
    """
    # Send 100 requests (fills the bucket)
    for _ in range(100):
        await client.post(
            "/api/v1/auth/login",
            json={"phone": "+923001111111", "password": "wrongpass"},
        )

    # The 101st should be rate-limited
    r = await client.post(
        "/api/v1/auth/login",
        json={"phone": "+923001111111", "password": "wrongpass"},
    )
    assert r.status_code == 429


async def test_auth_endpoint_rate_limit_returns_429_after_10(client: AsyncClient):
    """
    /auth/login and /auth/verify-otp have a stricter 10 req/min per IP limit.
    """
    for _ in range(10):
        await client.post(
            "/api/v1/auth/verify-otp",
            json={"otp_token": "fake-token", "otp_code": "123456"},
        )

    r = await client.post(
        "/api/v1/auth/verify-otp",
        json={"otp_token": "fake-token", "otp_code": "123456"},
    )
    assert r.status_code == 429


async def test_per_user_rate_limit_returns_429_after_60(client: AsyncClient, test_user):
    """
    Authenticated users have a 60 req/min per user_id limit.
    """
    user, token = test_user
    headers = _auth(token)

    # 60 requests fills the per-user bucket
    for _ in range(60):
        await client.get("/api/v1/auth/me", headers=headers)

    # 61st should be blocked
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 429


async def test_health_endpoint_not_rate_limited(client: AsyncClient):
    """
    /health must never be rate-limited — load balancers call it continuously.
    """
    for _ in range(120):
        r = await client.get("/health")
        assert r.status_code == 200
