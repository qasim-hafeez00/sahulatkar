import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_admin_contract_lists_return_paginated_shape(client: AsyncClient, test_admin):
    _, admin_token = test_admin

    wakalah = await client.get("/api/v1/contracts/admin/wakalah", headers=_auth(admin_token))
    assert wakalah.status_code == 200
    wakalah_body = wakalah.json()
    assert "items" in wakalah_body
    assert "pagination" in wakalah_body

    murabaha = await client.get("/api/v1/contracts/admin/murabaha", headers=_auth(admin_token))
    assert murabaha.status_code == 200
    murabaha_body = murabaha.json()
    assert "items" in murabaha_body
    assert "pagination" in murabaha_body