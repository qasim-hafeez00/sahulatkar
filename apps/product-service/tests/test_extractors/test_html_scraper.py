import socket
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from src.extractors.html_scraper import HtmlScraper
from src.services.url_normalizer import UrlNormalizerService


def test_json_ld_product_extracted():
    scraper = HtmlScraper()
    html = b'<html><script type="application/ld+json">{"@type":"Product","name":"Watch","offers":{"price":"1200","priceCurrency":"PKR","availability":"http://schema.org/InStock"}}</script></html>'
    data = scraper.extract_json_ld(html)
    assert data is not None
    assert data["title"] == "Watch"
    assert data["currency"] == "PKR"


def test_confidence_values_via_result_build():
    scraper = HtmlScraper()
    res = scraper._to_result({"title": "A", "price": "1", "currency": "PKR", "availability": "in_stock", "images": []}, Decimal("0.85"))
    assert res.confidence == Decimal("0.85")


@pytest.mark.asyncio
async def test_fetch_and_parse_rejects_url_unsafe_at_fetch_time():
    """SSRF/DNS-rebinding regression (Bug 1): `fetch_and_parse` is called
    asynchronously by the scraping worker, potentially long after the URL
    was already validated once at submission time. If the host is unsafe
    *right now* (e.g. DNS was rebound to a private/loopback/metadata IP
    since submission), the fetch must be refused outright rather than
    trusting the earlier one-time check."""
    fake_normalizer = AsyncMock(spec=UrlNormalizerService)
    fake_normalizer.resolve_pinned_request.side_effect = ValueError("UNSAFE_URL")
    scraper = HtmlScraper(url_normalizer=fake_normalizer)

    request_issued = False

    async def fake_get(self, url, **kwargs):
        nonlocal request_issued
        request_issued = True
        return httpx.Response(200, request=httpx.Request("GET", url))

    import unittest.mock as mock
    with mock.patch.object(httpx.AsyncClient, "get", new=fake_get):
        result = await scraper.fetch_and_parse("https://rebinding.example/product/123")

    assert result is None
    assert request_issued is False
    fake_normalizer.resolve_pinned_request.assert_awaited_once_with("https://rebinding.example/product/123")


@pytest.mark.asyncio
async def test_fetch_and_parse_rejects_dns_rebound_to_private_ip(monkeypatch):
    """End-to-end version of the same regression using the real
    UrlNormalizerService: a domain that now resolves to a private IP (even
    though it may have resolved publicly at submission time) must be
    rejected at fetch time, and no HTTP request may reach it."""

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr("src.services.url_normalizer.socket.getaddrinfo", fake_getaddrinfo)

    scraper = HtmlScraper()
    request_issued = False

    async def fake_get(self, url, **kwargs):
        nonlocal request_issued
        request_issued = True
        return httpx.Response(200, request=httpx.Request("GET", url))

    import unittest.mock as mock
    with mock.patch.object(httpx.AsyncClient, "get", new=fake_get):
        result = await scraper.fetch_and_parse("https://rebound-after-submit.example/product/9")

    assert result is None
    assert request_issued is False


@pytest.mark.asyncio
async def test_fetch_and_parse_pins_connection_to_validated_ip(monkeypatch):
    """When the host is safe, `fetch_and_parse` must still connect to the
    freshly-resolved/validated IP (not let httpx re-resolve DNS itself),
    mirroring the pinning technique `UrlNormalizerService` already uses at
    submission time - closing the fetch-time half of the same TOCTOU."""

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("src.services.url_normalizer.socket.getaddrinfo", fake_getaddrinfo)

    scraper = HtmlScraper()
    captured = {}

    async def fake_get(self, url, **kwargs):
        captured["url"] = str(url)
        captured["kwargs"] = kwargs
        return httpx.Response(200, request=httpx.Request("GET", url))

    import unittest.mock as mock
    with mock.patch.object(httpx.AsyncClient, "get", new=fake_get):
        await scraper.fetch_and_parse("https://safe-merchant.example/product/9")

    assert captured["url"].startswith("https://93.184.216.34")
    assert captured["kwargs"]["headers"]["Host"] == "safe-merchant.example"
    assert captured["kwargs"]["headers"]["User-Agent"] == HtmlScraper.USER_AGENT
