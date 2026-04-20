from datetime import datetime, timezone

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_contract_price_history_response_shape(client, make_product, db_session, service_header):
    product = await make_product(db_session, canonical_url="https://example.com/contract-history")
    await db_session.commit()

    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS product_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                old_price NUMERIC NOT NULL,
                new_price NUMERIC NOT NULL,
                changed_at TEXT NOT NULL
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO product_price_history (product_id, old_price, new_price, changed_at)
            VALUES (:product_id, :old_price, :new_price, :changed_at)
            """
        ),
        {
            "product_id": product.id,
            "old_price": "1000.00",
            "new_price": "1100.00",
            "changed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/price-history", headers=service_header)
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"product_id", "items"}
    assert isinstance(body["items"], list)
    assert set(body["items"][0].keys()) == {"old_price", "new_price", "changed_at"}


@pytest.mark.asyncio
async def test_contract_admin_queue_stats_includes_preview_fields(client, redis_mock, service_header):
    await redis_mock.redis.lpush(
        "sk:queue:dlq:checkout",
        '{"queue":"checkout","payload":{"order_id":100},"error":"boom","attempt":3,"moved_at":"2026-01-01T00:00:00Z"}',
    )

    res = await client.get("/api/v1/admin/queue-stats", headers=service_header)
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {
        "checkout_queue_depth",
        "scraping_queue_depth",
        "checkout_dlq_depth",
        "scraping_dlq_depth",
        "checkout_dlq_entries",
        "scraping_dlq_entries",
    }
    assert isinstance(body["checkout_dlq_entries"], list)
