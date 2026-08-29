from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from sk_shared.models.hitl import HitlQueue
from sk_shared.models.product import Product, ScrapingJob

from src.config import settings
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
    # HIGH-05: retries now sleep (exponential backoff) before re-queuing;
    # this test cares about the retry-then-fail state machine, not the
    # backoff timing itself, so mock the sleep out to keep it fast. The
    # actual backoff behavior is covered by the
    # test_scraping_worker_retry_backoff_* tests below.
    monkeypatch.setattr("src.workers.scraping_worker.asyncio.sleep", AsyncMock())

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
async def test_scraping_worker_retry_backoff_grows_and_is_capped(monkeypatch):
    """HIGH-05: retries must back off exponentially (base * 2^(attempt-1)),
    capped at EXTRACTION_RETRY_BACKOFF_MAX_SECONDS, instead of the old
    zero-delay instant re-queue that burned through the retry budget in a
    fraction of a second."""
    monkeypatch.setattr(settings, "EXTRACTION_RETRY_BACKOFF_BASE_SECONDS", 2.0)
    monkeypatch.setattr(settings, "EXTRACTION_RETRY_BACKOFF_MAX_SECONDS", 30.0)
    # Pin jitter to 0 so the assertions are exact.
    monkeypatch.setattr("src.workers.scraping_worker.random.uniform", lambda a, b: 0.0)

    # attempt 1 -> base * 2^0 = 2.0s
    assert ScrapingWorker._retry_backoff_seconds(1, False) == pytest.approx(2.0)
    # attempt 2 -> base * 2^1 = 4.0s
    assert ScrapingWorker._retry_backoff_seconds(2, False) == pytest.approx(4.0)
    # attempt 3 -> base * 2^2 = 8.0s
    assert ScrapingWorker._retry_backoff_seconds(3, False) == pytest.approx(8.0)
    # attempt 6 -> base * 2^5 = 64.0s, capped at 30.0s
    assert ScrapingWorker._retry_backoff_seconds(6, False) == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_scraping_worker_retry_backoff_longer_for_rate_limit(monkeypatch):
    """A 429 (detected via ExtractionWaterfallService.run_tier3 tagging the
    failure "RATE_LIMITED", surfaced to the worker in the waterfall's
    aggregated error_code/error_message -- see
    ScrapingWorker._is_rate_limited_result) must back off longer up front
    than a generic transient failure at the same attempt number."""
    monkeypatch.setattr(settings, "EXTRACTION_RETRY_BACKOFF_BASE_SECONDS", 2.0)
    monkeypatch.setattr(settings, "EXTRACTION_RETRY_BACKOFF_MAX_SECONDS", 300.0)
    monkeypatch.setattr("src.workers.scraping_worker.random.uniform", lambda a, b: 0.0)

    generic_delay = ScrapingWorker._retry_backoff_seconds(1, False)
    rate_limited_delay = ScrapingWorker._retry_backoff_seconds(1, True)

    assert rate_limited_delay > generic_delay
    assert rate_limited_delay == pytest.approx(generic_delay * 4)


def test_is_rate_limited_result_checks_code_and_message():
    """Covers both shapes a caller might see: a bare run_tier3() failure
    (error_code="RATE_LIMITED" directly) and the full waterfall's aggregated
    failure (error_code="EXTRACTION_FAILED" but "RATE_LIMITED" folded into
    error_message via the tier failures list)."""
    bare = ExtractionResult(
        status="failed", method="playwright_llm", confidence=Decimal("0"),
        title="", price=Decimal("0"), error_code="RATE_LIMITED", error_message="429",
    )
    aggregated = ExtractionResult(
        status="failed", method="waterfall", confidence=Decimal("0"),
        title="", price=Decimal("0"), error_code="EXTRACTION_FAILED",
        error_message="All extraction tiers failed: tier1:no_result | tier3:RATE_LIMITED",
    )
    generic = ExtractionResult(
        status="failed", method="waterfall", confidence=Decimal("0"),
        title="", price=Decimal("0"), error_code="EXTRACTION_FAILED",
        error_message="All extraction tiers failed: tier1:no_result | tier3:EXTRACTION_ERROR",
    )
    assert ScrapingWorker._is_rate_limited_result(bare) is True
    assert ScrapingWorker._is_rate_limited_result(aggregated) is True
    assert ScrapingWorker._is_rate_limited_result(generic) is False


@pytest.mark.asyncio
async def test_scraping_worker_sleeps_before_requeue_on_retry(monkeypatch, db_session, redis_mock):
    """End-to-end: _process() must actually await asyncio.sleep(...) with the
    computed backoff delay before re-queuing a failed job -- not just compute
    the delay and discard it."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("src.workers.scraping_worker.asyncio.sleep", sleep_mock)
    monkeypatch.setattr(settings, "EXTRACTION_RETRY_BACKOFF_BASE_SECONDS", 2.0)
    monkeypatch.setattr("src.workers.scraping_worker.random.uniform", lambda a, b: 0.0)

    job = ScrapingJob(
        input_url="https://example.com/rate-limited",
        canonical_url="https://example.com/rate-limited",
        platform_detected="CUSTOM",
        status="queued",
        attempt_number=1,
        max_attempts=3,
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.commit()

    async def rate_limited_tier3(self, canonical_url: str, platform: str, scrape_config: dict | None = None):
        return ExtractionResult(
            status="failed",
            method="playwright_llm",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
            error_code="RATE_LIMITED",
            error_message="429 Too Many Requests",
        )

    monkeypatch.setattr("src.services.extraction_waterfall.ExtractionWaterfallService.run_tier3", rate_limited_tier3)

    worker = ScrapingWorker(redis_mock)
    payload = {
        "job_id": job.uuid,
        "input_url": "https://example.com/rate-limited",
        "canonical_url": "https://example.com/rate-limited",
        "platform": "CUSTOM",
    }

    await worker._process(payload, db_session)

    sleep_mock.assert_awaited_once()
    (delay,), _ = sleep_mock.call_args
    # attempt 1, RATE_LIMITED -> base(2.0) * 4 * 2^0 = 8.0s (no jitter, pinned above)
    assert delay == pytest.approx(8.0)

    await db_session.refresh(job)
    assert job.status == "retrying"
    assert await redis_mock.redis.llen("sk:queue:scraping") == 1


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
