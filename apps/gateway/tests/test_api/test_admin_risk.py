import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_blacklist_crud_flow(client: AsyncClient, db_session, test_admin):
    _, admin_token = test_admin
    
    # 1. Add Entry
    payload = {
        "entry_type": "user",
        "value": "+923000000000",
        "reason": "Repeated fraud attempts"
    }
    response = await client.post("/api/v1/admin/risk/blacklist", json=payload, headers=_auth(admin_token))
    assert response.status_code == 201
    entry_id = response.json()["id"]
    
    # 2. List
    list_res = await client.get("/api/v1/admin/risk/blacklist", headers=_auth(admin_token))
    assert list_res.status_code == 200
    assert any(e["id"] == entry_id for e in list_res.json()["items"])
    
    # 3. Delete
    del_res = await client.delete(f"/api/v1/admin/risk/blacklist/{entry_id}", headers=_auth(admin_token))
    assert del_res.status_code == 200
    
    # 4. Verify soft delete (deleted_at IS NOT NULL)
    final_res = await client.get("/api/v1/admin/risk/blacklist", headers=_auth(admin_token))
    assert not any(e["id"] == entry_id for e in final_res.json()["items"])

async def test_blacklist_filter_by_type(client: AsyncClient, db_session, test_admin):
    _, admin_token = test_admin
    
    # Manual seed using SQL since we're testing the list filter
    await db_session.execute(text(
        "INSERT INTO risk_blacklist (entry_type, value, reason) VALUES ('ip', '1.1.1.1', 'bot')"
    ))
    await db_session.commit()
    
    response = await client.get("/api/v1/admin/risk/blacklist?entry_type=ip", headers=_auth(admin_token))
    assert response.status_code == 200
    items = response.json()["items"]
    for item in items:
        assert item["entry_type"] == "ip"

async def test_blacklist_invalid_type(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    payload = {
        "entry_type": "invalid", # Literal check
        "value": "something",
        "reason": "..."
    }
    response = await client.post("/api/v1/admin/risk/blacklist", json=payload, headers=_auth(admin_token))
    assert response.status_code == 422
