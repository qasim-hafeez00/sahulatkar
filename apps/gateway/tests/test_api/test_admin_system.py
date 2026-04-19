import pytest
from httpx import AsyncClient
import json

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_get_system_parameters_defaults(client: AsyncClient, test_admin, redis_mock):
    _, admin_token = test_admin
    
    # Ensure cache is clear
    await redis_mock.delete("sk:admin:system:parameters")
    
    response = await client.get("/api/v1/admin/system/parameters", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    
    assert "parameters" in data
    # Verify a couple of defaults
    assert data["parameters"]["max_credit_limit_pkr"] == 500000
    assert data["parameters"]["maintenance_mode"] is False
    assert data["parameters"]["require_admin_mfa"] is True
    assert data["cached"] is False

async def test_update_parameters_validation(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    
    # 1. Unknown key test
    payload = {"parameters": {"unknown_key": 123}}
    response = await client.put("/api/v1/admin/system/parameters", json=payload, headers=_auth(admin_token))
    assert response.status_code == 400
    assert "Unknown parameter keys" in response.json()["detail"]
    
    # 2. Valid key should upsert successfully with ORM-backed system_parameters table
    payload = {"parameters": {"maintenance_mode": True}}
    response = await client.put("/api/v1/admin/system/parameters", json=payload, headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "maintenance_mode" in data["updated"]

async def test_get_parameters_cached(client: AsyncClient, test_admin, redis_mock):
    _, admin_token = test_admin
    key = "sk:admin:system:parameters"
    
    fake_params = {"maintenance_mode": True, "custom": "value"}
    await redis_mock.set(key, json.dumps(fake_params), 300)
    
    response = await client.get("/api/v1/admin/system/parameters", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["parameters"]["maintenance_mode"] is True
    assert data["cached"] is True
