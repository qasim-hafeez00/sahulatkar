from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sk_shared.models.product import Product, ScrapingJob


@pytest.mark.asyncio
async def test_list_user_products_returns_only_current_user_items(client, db_session):
    p1 = Product(
        name="User One Product",
        url="https://example.com/u1",
        canonical_url="https://example.com/u1",
        platform="CUSTOM",
        currency="PKR",
        cost_price=Decimal("111.00"),
        sale_price=Decimal("111.00"),
        stock_status="in_stock",
        in_stock=True,
    )
    p2 = Product(
        name="User Two Product",
        url="https://example.com/u2",
        canonical_url="https://example.com/u2",
        platform="CUSTOM",
        currency="PKR",
        cost_price=Decimal("222.00"),
        sale_price=Decimal("222.00"),
        stock_status="in_stock",
        in_stock=True,
    )
    db_session.add_all([p1, p2])
    await db_session.flush()

    db_session.add(
        ScrapingJob(
            user_id=101,
            input_url=p1.url,
            canonical_url=p1.canonical_url,
            platform_detected="CUSTOM",
            status="completed",
            queued_at=datetime.now(timezone.utc),
            product_id=p1.id,
        )
    )
    db_session.add(
        ScrapingJob(
            user_id=202,
            input_url=p2.url,
            canonical_url=p2.canonical_url,
            platform_detected="CUSTOM",
            status="completed",
            queued_at=datetime.now(timezone.utc),
            product_id=p2.id,
        )
    )
    await db_session.commit()

    user_101_headers = {
        "x-user-id": "101",
        "X-Internal-Service-Token": "dev-secret-token",
    }
    res = await client.get("/api/v1/products", headers=user_101_headers)

    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "User One Product"


@pytest.mark.asyncio
async def test_list_user_products_cursor_pagination(client, db_session):
    products = [
        Product(
            name=f"User Product {idx}",
            url=f"https://example.com/u/{idx}",
            canonical_url=f"https://example.com/u/{idx}",
            platform="CUSTOM",
            currency="PKR",
            cost_price=Decimal("100.00") + Decimal(idx),
            sale_price=Decimal("100.00") + Decimal(idx),
            stock_status="in_stock",
            in_stock=True,
        )
        for idx in range(3)
    ]
    db_session.add_all(products)
    await db_session.flush()

    for product in products:
        db_session.add(
            ScrapingJob(
                user_id=700,
                input_url=product.url,
                canonical_url=product.canonical_url,
                platform_detected="CUSTOM",
                status="completed",
                queued_at=datetime.now(timezone.utc),
                product_id=product.id,
            )
        )
    await db_session.commit()

    headers = {
        "x-user-id": "700",
        "X-Internal-Service-Token": "dev-secret-token",
    }
    first = await client.get("/api/v1/products", params={"limit": 1}, headers=headers)

    assert first.status_code == 200
    first_body = first.json()
    assert first_body["total"] == 3
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/api/v1/products",
        params={"limit": 1, "cursor": first_body["next_cursor"]},
        headers=headers,
    )

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["total"] == 3
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["product_id"] != first_body["items"][0]["product_id"]


@pytest.mark.asyncio
async def test_list_user_products_invalid_cursor_returns_400(client):
    headers = {
        "x-user-id": "700",
        "X-Internal-Service-Token": "dev-secret-token",
    }
    res = await client.get("/api/v1/products", params={"cursor": "not-base64"}, headers=headers)

    assert res.status_code == 400
    assert res.json()["detail"] == "INVALID_CURSOR"