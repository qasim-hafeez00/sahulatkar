from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_search_returns_matching_items(client, db_session, make_product):
    await make_product(db_session, name="Noise Cancelling Headphones", canonical_url="https://example.com/headphones")
    await make_product(db_session, name="Phone Case", canonical_url="https://example.com/case")
    await db_session.commit()

    res = await client.get("/api/v1/products/search", params={"q": "head", "limit": 10})
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] >= 1
    assert any("Headphones" in item["name"] for item in payload["items"])


@pytest.mark.asyncio
async def test_search_requires_min_query_length(client):
    res = await client.get("/api/v1/products/search", params={"q": "a"})
    assert res.status_code == 422
