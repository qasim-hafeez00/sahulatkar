from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_integration_extract_then_fetch_offer(client, monkeypatch, user_header):
    from src.services.extraction_waterfall import ExtractionResult, ExtractionWaterfallService

    async def fake_extract(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.900"),
            title="Integration Product",
            price=Decimal("10000.00"),
            image_url=None,
        )

    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)

    extract = await client.post(
        "/api/v1/products/extract",
        headers=user_header,
        json={"raw_url": "https://example.com/integration/p1"},
    )
    assert extract.status_code == 200
    payload = extract.json()
    assert payload["status"] == "completed"

    product_id = payload["upo"]["product_id"]
    offer = await client.get(
        f"/api/v1/products/{product_id}/offer",
        params={"plan_months": 3, "down_payment_pct": 30},
    )
    assert offer.status_code == 200
    assert offer.json()["financing_offer"]["plan_months"] == 3
