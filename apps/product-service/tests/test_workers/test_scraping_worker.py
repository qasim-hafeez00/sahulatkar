from decimal import Decimal
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from sk_shared.models.hitl import HitlQueue
from sk_shared.models.product import Product, ScrapingJob

from src.services.extraction_waterfall import ExtractionResult
from src.services.prohibited_checker import ProhibitedDecision
from src.workers.scraping_worker import ScrapingWorker


@pytest.mark.asyncio
async def test_scraping_worker_processes_job(monkeypatch, db_session, redis_mock):
    job = ScrapingJob(
        input_url="https://example.com/item",
        canonical_url="https://example.com/item",
        platform_detected="CUSTOM",
        status="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    async def fake_tier3(self, canonical_url: str, platform: str, scrape_config: dict | None = None):
        return ExtractionResult(
            status="completed",
            method="playwright_llm",
            confidence=Decimal("0.777"),
            title="Generated Product",
            price=Decimal("9999.00"),
            image_url=None,
        )

    monkeypatch.setattr("src.services.extraction_waterfall.ExtractionWaterfallService.run_tier3", fake_tier3)

    worker = ScrapingWorker(redis_mock)
    await worker._process(
        {
            "job_id": job.uuid,
            "input_url": "https://example.com/item",
            "canonical_url": "https://example.com/item",
            "platform": "CUSTOM",
        },
        db_session
    )

    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.product_id is not None
    assert job.result["title"] == "Generated Product"


@pytest.mark.asyncio
async def test_scraping_worker_retries_then_fails(monkeypatch, db_session, redis_mock):
    job = ScrapingJob(
        input_url="https://example.com/fail",
        canonical_url="https://example.com/fail",
        platform_detected="CUSTOM",
        status="queued",
        attempt_number=1,
        max_attempts=2,
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    async def failing_tier3(self, canonical_url: str, platform: str, scrape_config: dict | None = None):
        return ExtractionResult(
            status="failed",
            method="playwright_llm",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
            error_code="EXTRACTION_FAILED",
            error_message="Simulated failure",
        )

    monkeypatch.setattr("src.services.extraction_waterfall.ExtractionWaterfallService.run_tier3", failing_tier3)

    worker = ScrapingWorker(redis_mock)
    payload = {
        "job_id": job.uuid,
        "input_url": "https://example.com/fail",
        "canonical_url": "https://example.com/fail",
        "platform": "CUSTOM",
    }

    await worker._process(payload, db_session)
    await db_session.refresh(job)
    assert job.status == "retrying"
    assert job.attempt_number == 2
    assert await redis_mock.redis.llen("sk:queue:scraping") == 1

    await worker._process(payload, db_session)
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "EXTRACTION_FAILED"


@pytest.mark.asyncio
async def test_scraping_worker_blocks_prohibited_product(monkeypatch, db_session, redis_mock):
    """P0-03: the async path must reject a prohibited product the same way
    the synchronous product_extraction_service path does — not save it as
    status="active"/purchasable and rely on the daily catalog sweep to catch
    it up to 24h later.
    """
    job = ScrapingJob(
        input_url="https://example.com/prohibited-item",
        canonical_url="https://example.com/prohibited-item",
        platform_detected="CUSTOM",
        status="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    async def fake_tier3(self, canonical_url: str, platform: str, scrape_config: dict | None = None):
        return ExtractionResult(
            status="completed",
            method="playwright_llm",
            confidence=Decimal("0.900"),
            title="Premium Whisky Gift Set",
            price=Decimal("4999.00"),
            image_url=None,
        )

    async def fake_check_text(self, **kwargs):
        return ProhibitedDecision(is_prohibited=True, category="alcohol", keyword="whisky", confidence=1.0)

    monkeypatch.setattr("src.services.extraction_waterfall.ExtractionWaterfallService.run_tier3", fake_tier3)
    monkeypatch.setattr("src.services.prohibited_checker.ProhibitedCheckerService.check_text", fake_check_text)

    worker = ScrapingWorker(redis_mock)
    await worker._process(
        {
            "job_id": job.uuid,
            "input_url": "https://example.com/prohibited-item",
            "canonical_url": "https://example.com/prohibited-item",
            "platform": "CUSTOM",
        },
        db_session,
    )

    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "PROHIBITED_CATEGORY"
    assert job.product_id is None

    # No Product row should have been created/upserted for a prohibited item.
    product = await db_session.scalar(
        select(Product).where(Product.canonical_url == "https://example.com/prohibited-item")
    )
    assert product is None

    # HITL escalation entry created (when FEATURE_HITL_ESCALATION is on, the
    # test-suite default — matches the synchronous path's behavior).
    from src.config import settings
    if settings.FEATURE_HITL_ESCALATION:
        hitl = await db_session.scalar(
            select(HitlQueue).where(HitlQueue.failure_reason.like("PROHIBITED_CATEGORY:%"))
        )
        assert hitl is not None
