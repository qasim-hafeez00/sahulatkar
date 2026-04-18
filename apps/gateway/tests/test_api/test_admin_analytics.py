import pytest
from httpx import AsyncClient
import json

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_gmv_trend_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/analytics/gmv-trend", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "series" in data

async def test_approval_funnel_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/analytics/approval-funnel?period=7d", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "7d"
    assert "steps" in data

async def test_analytics_caching(client: AsyncClient, test_admin, redis_mock):
    _, admin_token = test_admin
    key = "sk:admin:analytics:funnel:30d"
    
    # Pre-populate cache
    fake_data = {"period": "30d", "steps": {"completed": 10}, "cached": True}
    await redis_mock.set(key, json.dumps(fake_data), 600)
    
    response = await client.get("/api/v1/admin/analytics/approval-funnel", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["steps"]["completed"] == 10
    # Note: The actual endpoint doesn't add "cached": True to the returned dict, 
    # but it loads it from json.loads(cached).
    assert "steps" in data

async def test_credit_band_distribution(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/analytics/credit-band-distribution", headers=_auth(admin_token))
    assert response.status_code == 200
    assert "bands" in response.json()

async def test_analytics_forbidden_for_users(client: AsyncClient, test_user):
    _, token = test_user
    response = await client.get("/api/v1/admin/analytics/gmv-trend", headers=_auth(token))
    assert response.status_code in {401, 403}
