from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from src.config import settings

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
    asin: str | None = None
    platform_id: str | None = None


class UrlNormalizerService:
    async def normalize(self, raw_url: str) -> NormalizedUrl:
        expanded_url = await self.expand_url(raw_url.strip())
        parsed = urlparse(expanded_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("NOT_A_PRODUCT_URL")

        domain = parsed.netloc.lower().replace("www.", "")
        if not domain:
            raise ValueError("NOT_A_PRODUCT_URL")
        if self._is_private_or_local_host(domain):
            raise ValueError("UNSAFE_URL")
        if not parsed.path:
            raise ValueError("NOT_A_PRODUCT_URL")

        platform = self.detect_platform(domain, parsed.path)
        parsed = self._normalize_amazon(parsed, domain)
        page_type = self.classify_page_type(parsed)
        if page_type in {"category", "search"}:
            raise ValueError("NOT_A_PRODUCT_URL")

        canonical = self.strip_tracking(parsed)
        await self.verify_url(canonical)

        asin = self._extract_asin(parsed.path) if platform == "AMAZON" else None
        platform_id = self._extract_daraz_product_id(parsed.path) if platform == "DARAZ" else None
        return NormalizedUrl(
            raw_url=raw_url,
            canonical_url=canonical,
            domain=domain,
            platform=platform,
            asin=asin,
            platform_id=platform_id,
        )

    async def expand_url(self, url: str) -> str:
        """Follow all redirects to get final canonical URL."""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                resp = await client.head(url)
                return str(resp.url)
        except Exception:
            return url

    async def verify_url(self, canonical_url: str) -> None:
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                resp = await client.head(canonical_url)
            if settings.FEATURE_STRICT_URL_HEAD_CHECK and resp.status_code in {404, 410}:
                raise ValueError("PRODUCT_NOT_FOUND")
            if resp.status_code in {403, 429}:
                return
        except ValueError:
            raise
        except Exception:
            # Some merchants block bots or HEAD requests; extraction tiers can still succeed.
            return

    def strip_tracking(self, parsed) -> str:
        clean_query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in _TRACKING_KEYS]
        normalized = parsed._replace(query=urlencode(clean_query, doseq=True), fragment="")
        return urlunparse(normalized)

    def detect_platform(self, domain: str, path: str = "") -> str:
        path = path.lower()
        if "amazon." in domain:
            return "AMAZON"
        if domain.endswith("daraz.pk") or "daraz." in domain:
            return "DARAZ"
        if domain.endswith("homeshopping.pk"):
            return "CUSTOM"
        if domain.endswith("ishopping.pk"):
            return "CUSTOM"
        if domain.endswith("goto.com.pk"):
            return "CUSTOM"
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
        if "bigcommerce" in domain:
            return "BIGCOMMERCE"
        if "magento" in domain:
            return "MAGENTO"
        return "CUSTOM"

    def classify_page_type(self, parsed) -> str:
        path = (parsed.path or "").lower()
        query = (parsed.query or "").lower()

        product_markers = ("/dp/", "/product/", "/products/", "/p/", "/item/")
        category_markers = ("/collections/", "/category/", "/search")

        if any(marker in path for marker in product_markers):
            return "product"
        if any(marker in path for marker in category_markers):
            return "category"
        if "q=" in query or "s=" in query:
            return "search"
        return "unknown"

    def _normalize_amazon(self, parsed, domain: str):
        if "amazon." not in domain:
            return parsed
        asin = self._extract_asin(parsed.path)
        if not asin:
            return parsed
        return parsed._replace(path=f"/dp/{asin}")

    def _extract_asin(self, path: str) -> str | None:
        m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$)", path, flags=re.IGNORECASE)
        if not m:
            return None
        return m.group(1).upper()

    def _extract_daraz_product_id(self, path: str) -> str | None:
        # Example: /products/some-name-123456789.html
        m = re.search(r"/products/.+-(\d+)\.html$", path, flags=re.IGNORECASE)
        return m.group(1) if m else None

    def _is_private_or_local_host(self, domain: str) -> bool:
        host = (domain or "").strip().lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        if host.endswith(".local"):
            return True

        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        except ValueError:
            return False
