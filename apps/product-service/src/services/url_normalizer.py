from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.parse import urljoin

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
        raw_input = raw_url.strip()
        # A single cache, scoped to this call, ensures every host involved in
        # this normalize() flow (the raw input, any redirect hops, and the
        # final verify) is DNS-resolved at most once and that the very same
        # resolution result is what the outbound requests connect to. This
        # closes the DNS-rebinding TOCTOU window where a safety-check
        # resolution and the real connection's resolution could disagree.
        resolution_cache: dict[str, str | None] = {}
        await self._ensure_target_is_safe(raw_input, resolution_cache)

        expanded_url = await self.expand_url(raw_input, resolution_cache)
        parsed = urlparse(expanded_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("NOT_A_PRODUCT_URL")

        domain = (parsed.hostname or "").lower().replace("www.", "")
        if not domain:
            raise ValueError("NOT_A_PRODUCT_URL")
        await self._ensure_target_is_safe(expanded_url, resolution_cache)
        if not parsed.path:
            raise ValueError("NOT_A_PRODUCT_URL")

        platform = self.detect_platform(domain, parsed.path)
        parsed = self._normalize_amazon(parsed, domain)
        page_type = self.classify_page_type(parsed)
        if page_type in {"category", "search"}:
            raise ValueError("NOT_A_PRODUCT_URL")

        canonical = self.strip_tracking(parsed)
        await self.verify_url(canonical, resolution_cache)

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

    async def expand_url(self, url: str, resolution_cache: dict[str, str | None] | None = None) -> str:
        """Follow redirects one hop at a time so each target can be validated."""
        if resolution_cache is None:
            resolution_cache = {}
        current_url = url
        for _ in range(5):
            safe_url, request_kwargs = await self._resolve_pinned(current_url, resolution_cache)
            try:
                async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                    resp = await client.head(safe_url, **request_kwargs)
            except ValueError:
                raise
            except Exception:
                return current_url

            if resp.status_code in {301, 302, 303, 307, 308}:
                location = resp.headers.get("location")
                if not location:
                    return current_url
                current_url = urljoin(current_url, location)
                continue

            return current_url

        safe_url, request_kwargs = await self._resolve_pinned(current_url, resolution_cache)
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                await client.head(safe_url, **request_kwargs)
                # Note: intentionally return the original (hostname-based)
                # current_url here rather than resp.url, since resp.url would
                # reflect the pinned IP address we actually connected to.
                return current_url
        except ValueError:
            raise
        except Exception:
            return current_url

    async def verify_url(self, canonical_url: str, resolution_cache: dict[str, str | None] | None = None) -> None:
        safe_url, request_kwargs = await self._resolve_pinned(canonical_url, resolution_cache)
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=10.0) as client:
                resp = await client.head(safe_url, **request_kwargs)
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
        # Social-commerce storefronts (Instagram DM-based selling, etc.) have
        # no structured product page or checkout flow to automate at all —
        # ordering happens via DM negotiation with the seller. Flagging this
        # at platform-detection time lets the extraction waterfall skip
        # straight to HITL/manual-concierge instead of burning automated
        # attempts against a site that can never support them.
        if domain.endswith("instagram.com") or domain == "instagr.am":
            return "SOCIAL_COMMERCE"
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

    async def _ensure_target_is_safe(self, url: str, resolution_cache: dict[str, str | None] | None = None) -> None:
        """Validate that `url`'s host is safe to contact.

        This is a thin wrapper over `_resolve_pinned` for call sites that only
        need the validation gate and don't issue a request of their own right
        after (the request-issuing call sites use `_resolve_pinned` directly
        so they can pin their connection to the exact IP that was validated).
        """
        await self._resolve_pinned(url, resolution_cache)

    async def _resolve_pinned(
        self, url: str, resolution_cache: dict[str, str | None] | None = None
    ) -> tuple[str, dict]:
        """Resolve `url`'s host to an IP exactly once (reusing the cache
        across the whole normalize() flow when one is supplied), validate it
        isn't private/loopback/link-local/reserved, and return a
        (safe_url, request_kwargs) pair that pins any outbound httpx request
        to that exact validated IP.

        This is the fix for the DNS-rebinding TOCTOU: previously the safety
        check resolved DNS and validated the IP, but the actual httpx request
        re-resolved DNS independently by hostname, so an attacker controlling
        DNS for their domain could return a public IP for the check and a
        private/metadata IP (e.g. 169.254.169.254) moments later for the real
        connection. By resolving once and connecting directly to that IP
        (while still sending the original Host header and TLS SNI so the
        target's virtual-hosting/cert validation still works), there is no
        second resolution left for an attacker to race.
        """
        if resolution_cache is None:
            resolution_cache = {}

        parsed = urlparse(url)
        host = (parsed.hostname or "").strip().lower()
        if not host:
            raise ValueError("NOT_A_PRODUCT_URL")
        if self._is_private_or_local_host(host):
            raise ValueError("UNSAFE_URL")

        if host in resolution_cache:
            pinned_ip = resolution_cache[host]
        else:
            pinned_ip = await self._resolve_validated_ip(host)
            resolution_cache[host] = pinned_ip

        request_kwargs: dict = {}
        safe_url = url
        if pinned_ip is not None and pinned_ip != host:
            netloc_host = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
            netloc = netloc_host if parsed.port is None else f"{netloc_host}:{parsed.port}"
            safe_url = urlunparse(parsed._replace(netloc=netloc))
            host_header = host if parsed.port is None else f"{host}:{parsed.port}"
            request_kwargs["headers"] = {"Host": host_header}
            if parsed.scheme == "https":
                # Keep TLS SNI (and therefore certificate hostname
                # verification) pointed at the real hostname even though the
                # TCP connection itself is pinned to the validated IP.
                request_kwargs["extensions"] = {"sni_hostname": host}
        return safe_url, request_kwargs

    async def _resolve_validated_ip(self, host: str) -> str | None:
        """Resolve `host` via DNS exactly once and validate every address it
        returns is public. Returns the IP to pin the connection to.

        Returns None (no pinning possible) if `host` couldn't be resolved at
        all (e.g. no running event loop, or the lookup itself failed) --
        callers fall back to letting httpx resolve normally in that case,
        matching this method's previous fail-open behaviour for lookup
        failures.
        """
        try:
            ipaddress.ip_address(host)
            return host  # Already a literal IP; nothing to rebind.
        except ValueError:
            pass

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        try:
            infos = await loop.run_in_executor(
                None, lambda: socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            )
        except Exception:
            return None

        resolved_ips: list[str] = []
        for _, _, _, _, sockaddr in infos:
            try:
                ip = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("UNSAFE_URL")
            resolved_ips.append(str(ip))

        return resolved_ips[0] if resolved_ips else None
