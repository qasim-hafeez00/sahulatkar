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


@pytest.mark.asyncio
async def test_normalize_rejects_unsafe_localhost_url():
    service = UrlNormalizerService()

    with pytest.raises(ValueError) as exc:
        await service.normalize("https://localhost/products/demo")

    assert str(exc.value) == "UNSAFE_URL"


@pytest.mark.asyncio
async def test_normalize_rejects_link_local_metadata_ip():
    service = UrlNormalizerService()

    with pytest.raises(ValueError) as exc:
        await service.normalize("http://169.254.169.254/latest/meta-data/")

    assert str(exc.value) == "UNSAFE_URL"


@pytest.mark.asyncio
async def test_normalize_rejects_dns_private_resolution(monkeypatch):
    service = UrlNormalizerService()

    def fake_getaddrinfo(*_args, **_kwargs):
        return [
            (
                0,
                0,
                0,
                "",
                ("10.0.0.1", 0),
            )
        ]

    monkeypatch.setattr("src.services.url_normalizer.socket.getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError) as exc:
        await service.normalize("https://merchant.example/product/123")

    assert str(exc.value) == "UNSAFE_URL"


@pytest.mark.asyncio
async def test_normalize_rejects_empty_path_url():
    service = UrlNormalizerService()

    with pytest.raises(ValueError) as exc:
        await service.normalize("https://example.com")

    assert str(exc.value) == "NOT_A_PRODUCT_URL"
