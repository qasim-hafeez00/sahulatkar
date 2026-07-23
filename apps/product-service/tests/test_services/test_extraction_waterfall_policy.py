from decimal import Decimal

import pytest

from src.services.extraction_waterfall import ExtractionResult, ExtractionWaterfallService


@pytest.mark.asyncio
async def test_tier2b_low_confidence_falls_through_and_tier3_wins(monkeypatch):
    service = ExtractionWaterfallService()

    async def fake_tier1(*_args, **_kwargs):
        return None

    async def fake_tier2a(*_args, **_kwargs):
        return None

    async def fake_tier2b(*_args, **_kwargs):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.55"),
            title="Budget Phone",
            price=Decimal("25000.00"),
            availability="in_stock",
        )

    async def fake_tier3(*_args, **_kwargs):
        return ExtractionResult(
            status="completed",
            method="playwright_llm",
            confidence=Decimal("0.91"),
            title="Budget Phone",
            price=Decimal("25000.00"),
            availability="in_stock",
        )

    monkeypatch.setattr(service, "_tier1_rye", fake_tier1)
    monkeypatch.setattr(service, "_tier2a_violet", fake_tier2a)
    monkeypatch.setattr(service, "_tier2b_html", fake_tier2b)
    monkeypatch.setattr(service, "run_tier3", fake_tier3)

    result = await service.extract("https://example.com/products/phone", "CUSTOM")
    assert result.status == "completed"
    assert result.method == "playwright_llm"


@pytest.mark.asyncio
async def test_tier3_price_wildly_disagreeing_with_earlier_tier_is_rejected(monkeypatch):
    """P1: Tier 3 (LLM) is fed untrusted scraped text and could be manipulated
    (prompt injection) into hallucinating a price. If an earlier tier already
    saw a real (even below-confidence-threshold) price for this product, a
    wildly different Tier 3 price must not be trusted as the purchase cost
    basis — it should be rejected rather than silently accepted."""
    service = ExtractionWaterfallService()

    async def fake_tier1(*_args, **_kwargs):
        return None

    async def fake_tier2a(*_args, **_kwargs):
        return None

    async def fake_tier2b(*_args, **_kwargs):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.55"),  # below tier2b's threshold, falls through
            title="Budget Phone",
            price=Decimal("25000.00"),
            availability="in_stock",
        )

    async def fake_tier3_manipulated(*_args, **_kwargs):
        return ExtractionResult(
            status="completed",
            method="playwright_llm",
            confidence=Decimal("0.95"),
            title="Budget Phone",
            # 80% below the tier2b hint (25000) — still inside the valid
            # MIN/MAX product price range, isolating this test to the
            # cross-check rather than the separate price-range validation.
            price=Decimal("5000.00"),
            availability="in_stock",
        )

    monkeypatch.setattr(service, "_tier1_rye", fake_tier1)
    monkeypatch.setattr(service, "_tier2a_violet", fake_tier2a)
    monkeypatch.setattr(service, "_tier2b_html", fake_tier2b)
    monkeypatch.setattr(service, "run_tier3", fake_tier3_manipulated)

    result = await service.extract("https://example.com/products/phone", "CUSTOM")

    assert result.method != "playwright_llm"
    assert result.status in {"hitl_required", "failed"}


@pytest.mark.asyncio
async def test_all_tiers_fail_returns_hitl_required_when_enabled(monkeypatch):
    service = ExtractionWaterfallService()

    async def fake_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_tier1_rye", fake_none)
    monkeypatch.setattr(service, "_tier2a_violet", fake_none)
    monkeypatch.setattr(service, "_tier2b_html", fake_none)
    monkeypatch.setattr(service, "run_tier3", fake_none)

    result = await service.extract("https://example.com/product/unknown", "CUSTOM")
    assert result.status in {"hitl_required", "failed"}
    assert result.error_code == "EXTRACTION_FAILED"
