from decimal import Decimal
from datetime import datetime, timezone

import pytest

from sk_shared.models.product import ScrapingJob

from src.services.extraction_waterfall import ExtractionResult
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

    async def fake_tier3(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="completed",
            method="playwright_llm",
            confidence=Decimal("0.777"),
            title="Generated Product",
            price=Decimal("9999.00"),
            image_url=None,
        )

    monkeypatch.setattr("src.services.extraction_waterfall.ExtractionWaterfallService.run_tier3", fake_tier3)

    worker = ScrapingWorker(db_session, redis_mock)
    await worker._process(
        {
            "job_id": str(job.uuid),
            "input_url": "https://example.com/item",
            "canonical_url": "https://example.com/item",
            "platform": "CUSTOM",
        }
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

    async def failing_tier3(self, canonical_url: str, platform: str):
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

    worker = ScrapingWorker(db_session, redis_mock)
    payload = {
        "job_id": str(job.uuid),
        "input_url": "https://example.com/fail",
        "canonical_url": "https://example.com/fail",
        "platform": "CUSTOM",
    }

    await worker._process(payload)
    await db_session.refresh(job)
    assert job.status == "retrying"
    assert job.attempt_number == 2
    assert await redis_mock.redis.llen("sk:queue:scraping") == 1

    await worker._process(payload)
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_code == "EXTRACTION_FAILED"
