from decimal import Decimal
from datetime import datetime, timezone

import pytest

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.product import ProhibitedCategory, ScrapingJob


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
