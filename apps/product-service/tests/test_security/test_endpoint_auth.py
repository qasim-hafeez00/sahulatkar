import pytest


@pytest.mark.asyncio
async def test_admin_queue_stats_requires_service_token(client):
    res = await client.get("/api/v1/admin/queue-stats")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_price_history_requires_service_token(client, make_product, db_session):
    product = await make_product(db_session, canonical_url="https://example.com/security-history")
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/price-history")
    assert res.status_code == 403
