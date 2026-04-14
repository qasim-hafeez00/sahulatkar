from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "aff_id",
    "affiliate",
    "ref",
    "ref_src",
}


@dataclass(slots=True)
class NormalizedUrl:
    raw_url: str
    canonical_url: str
    domain: str
    platform: str


class UrlNormalizerService:
    async def normalize(self, raw_url: str) -> NormalizedUrl:
        expanded_url = await self.expand_url(raw_url.strip())
        parsed = urlparse(expanded_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("NOT_A_PRODUCT_URL")

        domain = parsed.netloc.lower().replace("www.", "")
        if not domain:
            raise ValueError("NOT_A_PRODUCT_URL")

        canonical = self.strip_tracking(parsed)
        platform = self.detect_platform(domain, parsed.path)
        return NormalizedUrl(raw_url=raw_url, canonical_url=canonical, domain=domain, platform=platform)

    async def expand_url(self, url: str) -> str:
        """Follow all redirects to get final canonical URL."""
        import httpx
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                resp = await client.head(url)
                return str(resp.url)
        except Exception:
            return url

    def strip_tracking(self, parsed) -> str:
        clean_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _TRACKING_KEYS]
        normalized = parsed._replace(query=urlencode(clean_query, doseq=True), fragment="")
        return urlunparse(normalized)

    def detect_platform(self, domain: str, path: str = "") -> str:
        path = path.lower()
        if "amazon." in domain:
            return "AMAZON"
        if "daraz." in domain:
            return "DARAZ"
        if "ebay." in domain:
            return "EBAY"
        if "aliexpress." in domain:
            return "ALIEXPRESS"
        if "myshopify.com" in domain or domain.endswith("shopify.com"):
            return "SHOPIFY"
        if "/products/" in path:  # Common Shopify pattern even with custom domains
            return "SHOPIFY"
        if "/product/" in path:
            return "WOOCOMMERCE"
        if "magento" in domain:
            return "MAGENTO"
        return "CUSTOM"
