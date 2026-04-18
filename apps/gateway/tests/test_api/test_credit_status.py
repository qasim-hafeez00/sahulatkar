"""
test_credit_status.py — Credit status endpoint.
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_credit_status_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/credit/status")
    assert r.status_code in {401, 403}


async def test_credit_status_returns_defaults_for_new_user(client: AsyncClient, test_user):
    _, token = test_user
    r = await client.get("/api/v1/credit/status", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert "credit_limit" in body
    assert "available_credit" in body
    assert "risk_band" in body
    assert "next_review_date" in body
    assert isinstance(body["credit_limit"], float)
    assert isinstance(body["available_credit"], float)


