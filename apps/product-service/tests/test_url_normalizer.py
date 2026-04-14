import pytest
from src.services.url_normalizer import UrlNormalizerService


@pytest.mark.asyncio
async def test_normalize_strips_tracking_and_detects_platform():
    service = UrlNormalizerService()
    normalized = await service.normalize(
        "https://www.amazon.com/Some-Product/dp/B0001?utm_source=x&aff_id=123&color=red#details"
    )

    assert normalized.platform == "AMAZON"
    assert "utm_source" not in normalized.canonical_url
    assert "aff_id" not in normalized.canonical_url
    assert "color=red" in normalized.canonical_url


@pytest.mark.asyncio
async def test_normalize_rejects_non_http_scheme():
    service = UrlNormalizerService()

    try:
        await service.normalize("ftp://example.com/product")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "NOT_A_PRODUCT_URL"
