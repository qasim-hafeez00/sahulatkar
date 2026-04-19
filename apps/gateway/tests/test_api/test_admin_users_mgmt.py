"""
test_admin_users_mgmt.py — Admin user status update, credit override, and sub-resource endpoints.
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_update_user_status_requires_admin(client: AsyncClient, test_user):
    user, token = test_user
    r = await client.put(
        f"/api/v1/admin/users/{user.id}/status",
        json={"status": "suspended"},
        headers=_auth(token),  # user token, not admin
    )
    assert r.status_code in {401, 403}


async def test_update_user_status_success(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin

    r = await client.put(
        f"/api/v1/admin/users/{user.id}/status",
        json={"status": "suspended"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "suspended"


async def test_update_user_status_invalid_value(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin

    r = await client.put(
        f"/api/v1/admin/users/{user.id}/status",
        json={"status": "deleted"},  # not in allowed enum
        headers=_auth(admin_token),
    )
    assert r.status_code == 422


async def test_update_user_status_404_for_unknown_user(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    r = await client.put(
        "/api/v1/admin/users/999999/status",
        json={"status": "active"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "USER_NOT_FOUND"


async def test_get_user_orders_returns_empty_list(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin

    r = await client.get(f"/api/v1/admin/users/{user.id}/orders", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "pagination" in body
    assert body["user_id"] == user.id
    assert isinstance(body["items"], list)


async def test_get_user_loans_returns_empty_list(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin

    r = await client.get(f"/api/v1/admin/users/{user.id}/loans", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["user_id"] == user.id


async def test_get_user_audit_log_returns_empty_list(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin

    r = await client.get(f"/api/v1/admin/users/{user.id}/audit-log", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["user_id"] == user.id


async def test_admin_list_users_returns_paginated_result(client: AsyncClient, test_user, test_admin):
    _, admin_token = test_admin
    r = await client.get("/api/v1/admin/users", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "pagination" in body


async def test_get_user_financial_summary(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin
    r = await client.get(f"/api/v1/admin/users/{user.id}/financial-summary", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == user.id
    assert "credit_limit" in body


async def test_get_user_kyc_summary(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin
    r = await client.get(f"/api/v1/admin/users/{user.id}/kyc", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == user.id
    assert "profile" in body


async def test_get_user_activity(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin
    r = await client.get(f"/api/v1/admin/users/{user.id}/activity", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == user.id
    assert "items" in body
