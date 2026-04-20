from decimal import Decimal
from datetime import datetime, timezone

import pytest

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.product import Merchant, Product, ProhibitedCategory, ScrapingJob


@pytest.mark.asyncio
async def test_admin_list_products_and_prohibit_unpromote(client, db_session, make_product, service_header):
    product = await make_product(db_session, name="Admin Product", cost_price=Decimal("2000.00"))
    await db_session.commit()

    listed = await client.get("/api/v1/admin/products", headers=service_header)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    prohibited = await client.post(f"/api/v1/admin/products/{product.uuid}/prohibit", headers=service_header)
    assert prohibited.status_code == 200

    unpromoted = await client.post(f"/api/v1/admin/products/{product.uuid}/unpromote", headers=service_header)
    assert unpromoted.status_code == 200
    assert unpromoted.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_patch_product_updates_fields(client, db_session, make_product, service_header):
    product = await make_product(
        db_session,
        name="Original Name",
        canonical_url="https://example.com/original",
        cost_price=Decimal("2000.00"),
    )
    await db_session.commit()

    res = await client.patch(
        f"/api/v1/admin/products/{product.uuid}",
        headers=service_header,
        json={
            "name": "Updated\u0000 Name",
            "canonical_url": "https://example.com/updated",
            "cost_price": "2100.00",
            "in_stock": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Updated Name"
    assert body["canonical_url"] == "https://example.com/updated"
    assert body["cost_price"] == "2100.00"

    await db_session.refresh(product)
    assert product.name == "Updated Name"
    assert str(product.cost_price) == "2100.00"
    assert product.in_stock is False


@pytest.mark.asyncio
async def test_admin_prohibited_categories_crud(client, service_header):
    create = await client.post(
        "/api/v1/admin/prohibited-categories",
        headers=service_header,
        json={"category_name": "Weapons", "keywords": ["gun", "rifle"]},
    )
    assert create.status_code == 200
    created_id = create.json()["id"]

    listed = await client.get("/api/v1/admin/prohibited-categories", headers=service_header)
    assert listed.status_code == 200
    assert any(item["category_name"] == "Weapons" for item in listed.json()["items"])

    deleted = await client.delete(f"/api/v1/admin/prohibited-categories/{created_id}", headers=service_header)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_admin_execution_retry_requeues(client, db_session, make_execution, redis_mock, service_header):
    execution = await make_execution(db_session, order_id=99, vcn_id=77, status="failed", step_reached="submit_payment")
    await db_session.commit()

    res = await client.post(f"/api/v1/admin/executions/{execution.uuid}/retry", headers=service_header)
    assert res.status_code == 200
    assert res.json()["status"] == "queued"

    queued = await redis_mock.redis.lindex("sk:queue:checkout", 0)
    assert queued is not None


@pytest.mark.asyncio
async def test_admin_execution_retry_rejects_succeeded(client, db_session, make_execution, service_header):
    execution = await make_execution(db_session, status="succeeded", step_reached="receipt")
    await db_session.commit()

    res = await client.post(f"/api/v1/admin/executions/{execution.uuid}/retry", headers=service_header)
    assert res.status_code == 409
    assert res.json()["detail"] == "EXECUTION_ALREADY_SUCCEEDED"


@pytest.mark.asyncio
async def test_admin_execution_retry_noop_for_running(client, db_session, make_execution, service_header):
    execution = await make_execution(db_session, status="running", step_reached="payment_injection")
    await db_session.commit()

    res = await client.post(f"/api/v1/admin/executions/{execution.uuid}/retry", headers=service_header)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "running"
    assert body["execution_id"] == str(execution.uuid)


@pytest.mark.asyncio
async def test_admin_scraping_jobs_total_respects_status_filter(client, db_session, service_header):
    db_session.add(
        ScrapingJob(
            input_url="https://example.com/1",
            canonical_url="https://example.com/1",
            platform_detected="CUSTOM",
            status="queued",
            queued_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        ScrapingJob(
            input_url="https://example.com/2",
            canonical_url="https://example.com/2",
            platform_detected="CUSTOM",
            status="failed",
            queued_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    res = await client.get("/api/v1/admin/scraping-jobs", headers=service_header, params={"status": "queued"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "queued"


@pytest.mark.asyncio
async def test_admin_merchants_list_detail_and_block(client, db_session, service_header):
    merchant = Merchant(
        name="Test Merchant",
        normalized_name="test merchant",
        domain="merchant.example",
        platform_type="CUSTOM",
        status="active",
        is_active=True,
    )
    db_session.add(merchant)
    await db_session.flush()

    product = Product(
        merchant_id=merchant.id,
        name="Merchant Product",
        url="https://merchant.example/p/1",
        canonical_url="https://merchant.example/p/1",
        platform="CUSTOM",
        currency="PKR",
        cost_price=Decimal("1000.00"),
        sale_price=Decimal("1000.00"),
        stock_status="in_stock",
        in_stock=True,
    )
    db_session.add(product)
    await db_session.commit()

    listed = await client.get("/api/v1/admin/merchants", headers=service_header)
    assert listed.status_code == 200
    list_body = listed.json()
    assert list_body["total"] >= 1
    assert any(item["domain"] == "merchant.example" for item in list_body["items"])

    detail = await client.get("/api/v1/admin/merchants/merchant.example", headers=service_header)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["domain"] == "merchant.example"
    assert detail_body["product_count"] == 1

    blocked = await client.post(
        "/api/v1/admin/merchants/merchant.example/block",
        headers=service_header,
        params={"reason": "fraud_risk"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["affected_products"] == 1

    await db_session.refresh(product)
    await db_session.refresh(merchant)
    assert merchant.status == "blocked"
    assert merchant.is_active is False
    assert product.is_prohibited is True
    assert product.prohibition_reason == "fraud_risk"


@pytest.mark.asyncio
async def test_admin_products_cursor_pagination(client, db_session, make_product, service_header):
    p1 = await make_product(db_session, name="Cursor Product A", canonical_url="https://example.com/cursor-a")
    p2 = await make_product(db_session, name="Cursor Product B", canonical_url="https://example.com/cursor-b")
    await db_session.commit()

    first = await client.get("/api/v1/admin/products", headers=service_header, params={"limit": 1})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/api/v1/admin/products",
        headers=service_header,
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["product_id"] != first_body["items"][0]["product_id"]


@pytest.mark.asyncio
async def test_admin_executions_cursor_pagination(client, db_session, make_execution, service_header):
    e1 = await make_execution(db_session, order_id=501, vcn_id=601)
    e2 = await make_execution(db_session, order_id=502, vcn_id=602)
    await db_session.commit()

    first = await client.get("/api/v1/admin/executions", headers=service_header, params={"limit": 1})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/api/v1/admin/executions",
        headers=service_header,
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["execution_id"] != first_body["items"][0]["execution_id"]


@pytest.mark.asyncio
async def test_admin_scraping_jobs_cursor_pagination(client, db_session, service_header):
    db_session.add(
        ScrapingJob(
            input_url="https://example.com/c1",
            canonical_url="https://example.com/c1",
            platform_detected="CUSTOM",
            status="queued",
            queued_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        ScrapingJob(
            input_url="https://example.com/c2",
            canonical_url="https://example.com/c2",
            platform_detected="CUSTOM",
            status="queued",
            queued_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    first = await client.get("/api/v1/admin/scraping-jobs", headers=service_header, params={"limit": 1})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/api/v1/admin/scraping-jobs",
        headers=service_header,
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["job_id"] != first_body["items"][0]["job_id"]


@pytest.mark.asyncio
async def test_admin_merchants_cursor_pagination(client, db_session, service_header):
    m1 = Merchant(
        name="Cursor Merchant A",
        normalized_name="cursor merchant a",
        domain="cursor-a.example",
        platform_type="CUSTOM",
        status="active",
        is_active=True,
    )
    m2 = Merchant(
        name="Cursor Merchant B",
        normalized_name="cursor merchant b",
        domain="cursor-b.example",
        platform_type="CUSTOM",
        status="active",
        is_active=True,
    )
    db_session.add(m1)
    db_session.add(m2)
    await db_session.commit()

    first = await client.get("/api/v1/admin/merchants", headers=service_header, params={"limit": 1})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None

    second = await client.get(
        "/api/v1/admin/merchants",
        headers=service_header,
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["items"][0]["merchant_id"] != first_body["items"][0]["merchant_id"]


@pytest.mark.asyncio
async def test_admin_cursor_rejects_invalid_value(client, service_header):
    res = await client.get("/api/v1/admin/products", headers=service_header, params={"cursor": "not-base64"})
    assert res.status_code == 400
    assert res.json()["detail"] == "INVALID_CURSOR"


@pytest.mark.asyncio
async def test_admin_queue_stats_includes_dlq_previews(client, redis_mock, service_header):
    await redis_mock.redis.lpush(
        "sk:queue:dlq:checkout",
        '{"queue":"checkout","payload":{"order_id":123},"error":"boom","attempt":3,"moved_at":"2026-01-01T00:00:00Z"}',
    )
    await redis_mock.redis.lpush(
        "sk:queue:dlq:scraping",
        '{"queue":"scraping","payload":{"job_id":"abc"},"error":"timeout","attempt":2,"moved_at":"2026-01-01T00:00:00Z"}',
    )

    res = await client.get("/api/v1/admin/queue-stats", headers=service_header)
    assert res.status_code == 200
    body = res.json()
    assert "checkout_dlq_entries" in body
    assert "scraping_dlq_entries" in body
    assert len(body["checkout_dlq_entries"]) >= 1
    assert len(body["scraping_dlq_entries"]) >= 1
