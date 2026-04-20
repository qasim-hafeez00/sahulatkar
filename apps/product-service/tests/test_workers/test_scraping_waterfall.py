"""DESIGN-03 Regression Tests — Scraping Worker uses full waterfall.

Verifies that ScrapingWorker._process() calls ExtractionWaterfallService.extract()
(the full Tier1→Tier2A→Tier2B→Tier3 waterfall) and NOT run_tier3() directly.

The old code always went straight to Playwright, bypassing fast-path Rye and
Violet APIs for platforms that support them (e.g. Shopify would take 30-45s
instead of <1s via Rye).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.extraction_waterfall import ExtractionWaterfallService


@pytest.mark.asyncio
async def test_scraping_worker_calls_extract_not_run_tier3(db_session, redis_mock, make_scraping_job):
    """DESIGN-03: worker must call extract() not run_tier3() directly."""
    from src.workers.scraping_worker import ScrapingWorker
    from src.services.extraction_waterfall import ExtractionResult

    job = await make_scraping_job(
        db_session,
        input_url="https://shopify-store.com/products/test",
        canonical_url="https://shopify-store.com/products/test",
        platform_detected="SHOPIFY",
        status="queued",
    )
    await db_session.commit()

    extract_called = {"count": 0}
    tier3_called = {"count": 0}

    async def fake_extract(self, canonical_url: str, platform: str):
        extract_called["count"] += 1
        return ExtractionResult(
            status="completed",
            method="rye_api",
            confidence=Decimal("0.98"),
            title="Fast Path Shopify Product",
            price=Decimal("3500.00"),
            image_url=None,
            availability="in_stock",
        )

    async def fake_tier3(self, canonical_url: str, platform: str):
        tier3_called["count"] += 1
        return ExtractionResult(
            status="failed",
            method="playwright_llm",
            confidence=Decimal("0"),
            title="",
            price=Decimal("0"),
            image_url=None,
        )

    payload = {
        "job_id": str(job.uuid),
        "input_url": job.input_url,
        "canonical_url": job.canonical_url,
        "platform": job.platform_detected,
    }

    with patch.object(ExtractionWaterfallService, "extract", fake_extract), \
         patch.object(ExtractionWaterfallService, "run_tier3", fake_tier3):
        worker = ScrapingWorker(redis_mock)
        await worker._process(payload, db_session)

    assert extract_called["count"] == 1, (
        "DESIGN-03: ScrapingWorker._process() must call service.extract() "
        "not service.run_tier3() directly."
    )
    assert tier3_called["count"] == 0, (
        "run_tier3() must NOT be called directly — it should only be invoked "
        "by the waterfall internally when faster tiers fail."
    )
