"""GAP-C Integration Tests — /extract Endpoint Rate Limiting.

Verifies that the /extract endpoint returns HTTP 429 with a Retry-After header
after exceeding the per-user rate limit, and that a different user/IP is not
affected by another user's limit.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_extract_rate_limit_blocks_after_limit_exceeded(client, user_header, monkeypatch):
    """After EXTRACT_RATE_LIMIT_PER_MINUTE requests, the endpoint returns 429."""
    from src.config import settings
    from src.services.extraction_waterfall import ExtractionWaterfallService, ExtractionResult
    from src.services.url_normalizer import UrlNormalizerService, NormalizedUrl

    # Lower limit to 2 for test speed
    monkeypatch.setattr(settings, "EXTRACT_RATE_LIMIT_PER_MINUTE", 2)

    async def fast_normalize(self, url: str):
        return NormalizedUrl(
            raw_url=url,
            canonical_url=url,
            domain="example.com",
            platform="CUSTOM",
        )

    async def fast_extract(self, url: str, platform: str, scrape_config=None):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.85"),
            title="Rate Limit Test Product",
            price=Decimal("1000.00"),
            image_url=None,
            availability="in_stock",
        )

    with patch.object(UrlNormalizerService, "normalize", fast_normalize), \
         patch.object(ExtractionWaterfallService, "extract", fast_extract):

        payload = {"raw_url": "https://example.com/product/ratelimit-test"}

        r1 = await client.post("/api/v1/products/extract", headers=user_header, json=payload)
        r2 = await client.post("/api/v1/products/extract", headers=user_header, json=payload)
        r3 = await client.post("/api/v1/products/extract", headers=user_header, json=payload)

    assert r1.status_code in (200, 422), f"First request should succeed, got {r1.status_code}"
    assert r2.status_code in (200, 422), f"Second request should succeed, got {r2.status_code}"
    assert r3.status_code == 429, (
        f"Third request (over limit=2) must return 429, got {r3.status_code}. "
        "Rate limiting is not enforced on the /extract endpoint."
    )
    assert r3.json()["detail"] == "EXTRACT_RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in r3.headers, "429 response must include Retry-After header"


@pytest.mark.asyncio
async def test_extract_rate_limit_is_per_user_not_global(client, monkeypatch):
    """Rate limit is tracked independently per user — different users don't share quota."""
    from src.config import settings
    from src.services.extraction_waterfall import ExtractionWaterfallService, ExtractionResult
    from src.services.url_normalizer import UrlNormalizerService, NormalizedUrl

    monkeypatch.setattr(settings, "EXTRACT_RATE_LIMIT_PER_MINUTE", 1)

    async def fast_normalize(self, url: str):
        return NormalizedUrl(raw_url=url, canonical_url=url, domain="example.com", platform="CUSTOM")

    async def fast_extract(self, url: str, platform: str, scrape_config=None):
        return ExtractionResult(
            status="completed", method="json_ld", confidence=Decimal("0.85"),
            title="Product", price=Decimal("500.00"), image_url=None, availability="in_stock",
        )

    with patch.object(UrlNormalizerService, "normalize", fast_normalize), \
         patch.object(ExtractionWaterfallService, "extract", fast_extract):

        payload = {"raw_url": "https://example.com/product/per-user-test"}
        user_a = {"x-user-id": "201", "X-Internal-Service-Token": "dev-secret-token"}
        user_b = {"x-user-id": "202", "X-Internal-Service-Token": "dev-secret-token"}

        # User A exhausts their quota
        await client.post("/api/v1/products/extract", headers=user_a, json=payload)
        r_a_over = await client.post("/api/v1/products/extract", headers=user_a, json=payload)

        # User B should still succeed
        r_b = await client.post("/api/v1/products/extract", headers=user_b, json=payload)

    assert r_a_over.status_code == 429, "User A should be rate limited"
    assert r_b.status_code in (200, 422), (
        f"User B must NOT be limited by User A's quota. Got {r_b.status_code}."
    )


@pytest.mark.asyncio
async def test_extract_rate_limit_prefers_x_real_ip_when_user_missing(client, monkeypatch):
    """When x-user-id is absent, limiter should bucket by x-real-ip."""
    from src.config import settings
    from src.services.extraction_waterfall import ExtractionWaterfallService, ExtractionResult
    from src.services.url_normalizer import UrlNormalizerService, NormalizedUrl

    monkeypatch.setattr(settings, "EXTRACT_RATE_LIMIT_PER_MINUTE", 1)

    async def fast_normalize(self, url: str):
        return NormalizedUrl(raw_url=url, canonical_url=url, domain="example.com", platform="CUSTOM")

    async def fast_extract(self, url: str, platform: str, scrape_config=None):
        return ExtractionResult(
            status="completed", method="json_ld", confidence=Decimal("0.85"),
            title="Product", price=Decimal("500.00"), image_url=None, availability="in_stock",
        )

    with patch.object(UrlNormalizerService, "normalize", fast_normalize), \
         patch.object(ExtractionWaterfallService, "extract", fast_extract):

        payload = {"raw_url": "https://example.com/product/ip-test"}
        h1 = {"X-Internal-Service-Token": "dev-secret-token", "X-Real-IP": "203.0.113.10"}
        h2 = {"X-Internal-Service-Token": "dev-secret-token", "X-Real-IP": "203.0.113.11"}

        r1 = await client.post("/api/v1/products/extract", headers=h1, json=payload)
        r1_over = await client.post("/api/v1/products/extract", headers=h1, json=payload)
        r2 = await client.post("/api/v1/products/extract", headers=h2, json=payload)

    assert r1.status_code in (200, 422)
    assert r1_over.status_code == 429, "Same x-real-ip should hit the same limiter bucket"
    assert r2.status_code in (200, 422), "Different x-real-ip should have independent quota"
