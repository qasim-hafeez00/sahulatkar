from decimal import Decimal

import pytest
from sqlalchemy import func, select

from sk_shared.models.product import Product


@pytest.mark.asyncio
async def test_extract_race_creates_single_product(client, db_session, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult
    from src.services.extraction_waterfall import ExtractionWaterfallService

    async def slow_extract(self, canonical_url: str, platform: str, scrape_config=None):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.800"),
            title="Race Product",
            price=Decimal("999.00"),
            image_url=None,
        )

    monkeypatch.setattr(ExtractionWaterfallService, "extract", slow_extract)

    payload = {"raw_url": "https://example.com/race-product?utm_source=abc"}
    first = await client.post("/api/v1/products/extract", headers=user_header, json=payload)
    second = await client.post("/api/v1/products/extract", headers=user_header, json=payload)

    assert first.status_code in {200, 409}
    assert second.status_code in {200, 409}

    product_count = await db_session.scalar(
        select(func.count(Product.id)).where(Product.canonical_url == "https://example.com/race-product")
    )
    assert product_count == 1
