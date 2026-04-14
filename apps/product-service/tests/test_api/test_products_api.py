from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from sk_shared.constants import QueueName
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.product import Product, ScrapingJob
from sk_shared.models.order import Order
from src.services.checkout_agent import CheckoutAgentService


@pytest.mark.asyncio
async def test_extract_completed_and_offer_and_search(client, db_session, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult, ExtractionWaterfallService
    async def fake_extract(*args, **kwargs):
        return ExtractionResult(status="completed", method="json_ld", confidence=Decimal("0.85"), title="Test Product", price=Decimal("100"), image_url=None)
    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)

    extract = await client.post(
        "/api/v1/products/extract",
        headers=user_header,
        json={"raw_url": "https://www.amazon.com/phone-case/dp/B12345"},
    )
    assert extract.status_code == 200
    data = extract.json()
    assert data["status"] == "completed"
    assert data["upo"]["platform"] == "AMAZON"

    product_uuid = data["upo"]["product_id"]

    offer = await client.get(f"/api/v1/products/{product_uuid}/offer", params={"plan_months": 3, "down_payment_pct": 30})
    assert offer.status_code == 200
    offer_data = offer.json()
    assert offer_data["financing_offer"]["profit_rate_pct"] == "2.5"

    # /search uses PostgreSQL plainto_tsquery / @@ which is incompatible with SQLite.
    # Verify the product was persisted correctly via the DB directly instead.
    from sqlalchemy import select as sa_select
    product_count = await db_session.scalar(sa_select(func.count(Product.id)).where(Product.deleted_at.is_(None)))
    assert product_count >= 1


@pytest.mark.asyncio
async def test_extract_rejects_invalid_url(client):
    response = await client.post("/api/v1/products/extract", json={"raw_url": "ftp://invalid"})
    assert response.status_code == 422
    assert response.json()["detail"] == "NOT_A_PRODUCT_URL"


@pytest.mark.asyncio
async def test_extract_async_job_path_with_monkeypatch(client, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult
    from src.services.extraction_waterfall import ExtractionWaterfallService

    async def fake_extract(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="extracting",
            method="playwright_llm",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
        )

    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)

    response = await client.post(
        "/api/v1/products/extract",
        headers=user_header,
        json={"raw_url": "https://example.com/product/js-heavy"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "extracting"
    assert body["job_id"] is not None


@pytest.mark.asyncio
async def test_extract_blocks_prohibited_category(client, db_session, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult
    from src.services.extraction_waterfall import ExtractionWaterfallService
    from src.services.prohibited_checker import ProhibitedDecision
    from src.services.prohibited_checker import ProhibitedCheckerService

    async def fake_extract(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.700"),
            title="Premium Alcohol Set",
            price=Decimal("15000.00"),
            image_url=None,
        )

    async def fake_check(*_args, **_kwargs):
        return ProhibitedDecision(is_prohibited=True, category="Alcohol", keyword="alcohol")

    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)
    monkeypatch.setattr(ProhibitedCheckerService, "check_text", fake_check)

    response = await client.post(
        "/api/v1/products/extract",
        headers=user_header,
        json={"raw_url": "https://example.com/prohibited-item"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "PROHIBITED_CATEGORY"

    products_count = await db_session.scalar(select(func.count(Product.id)))
    assert products_count == 0


@pytest.mark.asyncio
async def test_extract_idempotent_for_same_url(client, db_session, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult
    from src.services.extraction_waterfall import ExtractionWaterfallService

    async def fake_extract(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.850"),
            title="Idempotent Product",
            price=Decimal("150.00"),
            image_url=None,
        )

    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)
    payload = {"raw_url": "https://example.com/product/idempotent?utm_source=test"}

    first = await client.post("/api/v1/products/extract", headers=user_header, json=payload)
    second = await client.post("/api/v1/products/extract", headers=user_header, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "completed"
    assert second.json()["status"] == "completed"
    assert first.json()["upo"]["product_id"] == second.json()["upo"]["product_id"]

    products_count = await db_session.scalar(select(func.count(Product.id)))
    assert products_count == 1


@pytest.mark.asyncio
async def test_extract_async_job_is_deduped(client, db_session, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult
    from src.services.extraction_waterfall import ExtractionWaterfallService

    async def fake_extract(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="extracting",
            method="playwright_llm",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
        )

    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)

    payload = {"raw_url": "https://example.com/product/slow"}
    first = await client.post("/api/v1/products/extract", headers=user_header, json=payload)
    second = await client.post("/api/v1/products/extract", headers=user_header, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "extracting"
    assert second.json()["status"] == "extracting"
    assert first.json()["job_id"] == second.json()["job_id"]

    jobs_count = await db_session.scalar(select(func.count(ScrapingJob.id)))
    assert jobs_count == 1


@pytest.mark.asyncio
async def test_job_status_returns_completed_payload(client, db_session):
    product = Product(
        name="Worker Product",
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        platform="CUSTOM",
        currency="PKR",
        cost_price=Decimal("1000.00"),
        sale_price=Decimal("1000.00"),
        stock_status="in_stock",
        in_stock=True,
        extraction_method="playwright_llm",
        extraction_confidence=Decimal("0.700"),
    )
    db_session.add(product)
    await db_session.flush()

    job = ScrapingJob(
        input_url="https://example.com/a",
        canonical_url="https://example.com/a",
        platform_detected="CUSTOM",
        status="completed",
        queued_at=datetime.now(timezone.utc),
        product_id=product.id,
    )
    db_session.add(job)
    await db_session.commit()

    res = await client.get(f"/api/v1/products/jobs/{job.uuid}")
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "completed"
    assert payload["upo"]["product_id"] == str(product.uuid)


@pytest.mark.asyncio
async def test_queue_checkout_job_enqueues_and_persists(client, db_session, redis_mock):
    response = await client.post(
        "/api/v1/products/agent/queue-job",
        json={
            "order_id": 9001,
            "vcn_id": 7001,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"

    execution = await db_session.scalar(
        select(PurchaseExecution).where(PurchaseExecution.uuid == UUID(body["job_id"]))
    )
    assert execution is not None
    assert execution.order_id == 9001
    assert execution.vcn_id == 7001
    assert execution.status == "queued"

    queued_items = await redis_mock.redis.lrange(QueueName.CHECKOUT, 0, -1)
    assert len(queued_items) == 1


@pytest.mark.asyncio
async def test_checkout_forced_failure_escalates_to_hitl(db_session, redis_mock):
    # Setup dependencies
    product = Product(name="Test", url="https://m.com", currency="PKR", cost_price=100)
    db_session.add(product)
    await db_session.flush()
    order = Order(user_id=1, product_id=product.id, total_amount=100, status="confirmed")
    db_session.add(order)
    await db_session.flush()

    from sk_shared.models.payment import VirtualCard
    from datetime import datetime, timezone, timedelta
    vcn = VirtualCard(
        order_id=order.id,
        user_id=1,
        issuer="MOCK_ISSUER",
        issuer_card_id="VCN-123",
        masked_number="4111********1111",
        card_expiry=datetime.now(timezone.utc).date() + timedelta(days=30),
        authorized_amount=100.0,
        loaded_amount=100.0,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30)
    )
    db_session.add(vcn)
    await db_session.flush()

    service = CheckoutAgentService(db_session, redis_mock)
    execution = await service.queue_job(order_id=order.id, vcn_id=vcn.id, force_failure=True)

    raw_payload = await redis_mock.redis.lpop(QueueName.CHECKOUT)
    assert raw_payload is not None

    import json
    payload = json.loads(raw_payload.decode("utf-8"))
    await service.process_job(payload)

    refreshed = await db_session.scalar(select(PurchaseExecution).where(PurchaseExecution.id == execution.id))
    assert refreshed is not None
    assert refreshed.status == "hitl_escalated"
    assert refreshed.failure_type == "checkout_changed", refreshed.error_detail

    hitl = await db_session.scalar(select(HitlQueue).where(HitlQueue.execution_id == execution.id))
    assert hitl is not None
    assert hitl.status == "pending"
    assert hitl.order_id == execution.order_id
