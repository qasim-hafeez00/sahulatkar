import socket
from urllib.parse import urlparse

import httpx
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


@pytest.mark.asyncio
async def test_normalize_blocks_dns_rebinding_to_metadata_ip(monkeypatch):
    """DNS-rebinding TOCTOU: a domain that resolves to a PUBLIC ip during the
    safety check but would resolve to a PRIVATE/metadata ip on any
    subsequent lookup must still be blocked, because the fix resolves DNS
    exactly once per host and reuses that single result for the outbound
    request instead of re-resolving at connect time.
    """
    service = UrlNormalizerService()

    public_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    # Anything beyond the first lookup returns the attacker's metadata ip -
    # if the code ever re-resolves, this is what it would (unsafely) connect to.
    metadata_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    call_count = {"n": 0}

    def fake_getaddrinfo(host, *args, **kwargs):
        call_count["n"] += 1
        return public_result if call_count["n"] == 1 else metadata_result

    monkeypatch.setattr("src.services.url_normalizer.socket.getaddrinfo", fake_getaddrinfo)

    captured_requests = []

    async def fake_head(self, url, **kwargs):
        captured_requests.append((str(url), kwargs))
        return httpx.Response(200, request=httpx.Request("HEAD", url))

    monkeypatch.setattr(httpx.AsyncClient, "head", fake_head)

    normalized = await service.normalize("https://rebinding.example/product/123")

    # DNS must have been resolved exactly once for this host, and reused for
    # every subsequent check/request in the flow - not re-resolved.
    assert call_count["n"] == 1

    # The outbound request(s) must have connected to the IP validated by
    # that single resolution (the public one), never to a fresh lookup.
    assert captured_requests
    for url, kwargs in captured_requests:
        assert urlparse(url).hostname == "93.184.216.34"
        assert kwargs.get("headers", {}).get("Host") == "rebinding.example"
        assert kwargs.get("extensions", {}).get("sni_hostname") == "rebinding.example"

    assert normalized.domain == "rebinding.example"


@pytest.mark.asyncio
async def test_normalize_blocks_when_only_resolution_is_private(monkeypatch):
    """If the single DNS resolution performed returns a private/metadata ip,
    the request must be blocked outright and no outbound HTTP request may be
    issued at all.
    """
    service = UrlNormalizerService()

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr("src.services.url_normalizer.socket.getaddrinfo", fake_getaddrinfo)

    request_issued = False

    async def fake_head(self, url, **kwargs):
        nonlocal request_issued
        request_issued = True
        return httpx.Response(200, request=httpx.Request("HEAD", url))

    monkeypatch.setattr(httpx.AsyncClient, "head", fake_head)

    with pytest.raises(ValueError) as exc:
        await service.normalize("https://attacker-controlled.example/product/1")

    assert str(exc.value) == "UNSAFE_URL"
    assert request_issued is False
