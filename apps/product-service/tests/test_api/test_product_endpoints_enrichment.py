from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.product import Product, ScrapingJob


@pytest.mark.asyncio
async def test_search_products_cursor_paginates(client, make_product, db_session):
    first = await make_product(db_session, name="Cursor Widget Alpha", canonical_url="https://example.com/a")
    second = await make_product(db_session, name="Cursor Widget Beta", canonical_url="https://example.com/b")
    await db_session.commit()

    first_page = await client.get("/api/v1/products/search", params={"q": "Cursor", "limit": 1})
    assert first_page.status_code == 200
    body = first_page.json()
    assert body["total"] >= 2
    assert len(body["items"]) == 1
    assert body["next_cursor"] is not None

    second_page = await client.get(
        "/api/v1/products/search",
        params={"q": "Cursor", "limit": 1, "cursor": body["next_cursor"]},
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["product_id"] != body["items"][0]["product_id"]


@pytest.mark.asyncio
async def test_product_detail_includes_jobs_and_executions(client, make_product, make_scraping_job, db_session):
    product = await make_product(
        db_session,
        name="Detail Product",
        canonical_url="https://example.com/detail",
        brand="DetailBrand",
        description="Detail description",
        variants=[{"option_name": "Color", "selected_value": "Black", "available": True}],
    )
    await make_scraping_job(
        db_session,
        product_id=product.id,
        order_id=444,
        status="completed",
        platform_detected="CUSTOM",
    )
    execution = PurchaseExecution(
        order_id=444,
        vcn_id=12,
        status="succeeded",
        step_reached="order_confirmed",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    response = await client.get(f"/api/v1/products/{product.uuid}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["brand"] == "DetailBrand"
    assert payload["meta"]["description"] == "Detail description"
    assert len(payload["scraping_jobs"]) == 1
    assert len(payload["checkout_executions"]) == 1


@pytest.mark.asyncio
async def test_prohibit_product_reason_is_in_body(client, make_product, db_session, service_header):
    product = await make_product(db_session, name="Prohibit Me")
    await db_session.commit()

    response = await client.post(
        f"/api/v1/admin/products/{product.uuid}/prohibit",
        headers=service_header,
        json={"reason": "Non-compliant product"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "prohibited"

    await db_session.refresh(product)
    refreshed = await db_session.scalar(select(Product).where(Product.id == product.id))
    assert refreshed is not None
    assert refreshed.is_prohibited is True
    assert refreshed.prohibition_reason == "Non-compliant product"
