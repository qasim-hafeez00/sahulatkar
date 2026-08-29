from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import re

import httpx
from bs4 import BeautifulSoup

from src.services.url_normalizer import UrlNormalizerService


@dataclass(slots=True)
class HtmlScrapeResult:
    title: str
    price: Decimal
    currency: str
    availability: str
    images: list[str]
    description: str | None
    confidence: Decimal


class HtmlScraper:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

    def __init__(self, url_normalizer: UrlNormalizerService | None = None) -> None:
        # `url` here has typically already passed UrlNormalizerService.normalize()
        # at submission time (POST /products/extract), but this fetch can
        # happen much later — asynchronously off `sk:queue:scraping`, after
        # retries/DLQ backoff — so DNS could have been rebound since then
        # (e.g. to the 169.254.169.254 metadata IP). Re-resolve and pin the
        # connection to a freshly-validated IP right here, immediately before
        # connecting, instead of trusting the one-time submission check.
        self._url_normalizer = url_normalizer or UrlNormalizerService()

    async def fetch_and_parse(self, url: str) -> HtmlScrapeResult | None:
        try:
            safe_url, pin_kwargs = await self._url_normalizer.resolve_pinned_request(url)
        except ValueError:
            # Host is unsafe right now (e.g. DNS-rebound to a private/
            # loopback/link-local/reserved IP since submission-time
            # validation) - refuse to fetch rather than trusting the earlier
            # check.
            return None

        headers = {"User-Agent": self.USER_AGENT, **pin_kwargs.pop("headers", {})}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(safe_url, headers=headers, **pin_kwargs)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        html_bytes = resp.content
        data = self.extract_json_ld(html_bytes)
        if data:
            return self._to_result(data, Decimal("0.85"))

        data = self.extract_opengraph(html_bytes)
        if data:
            return self._to_result(data, Decimal("0.65"))

        data = self.extract_meta_tags(html_bytes)
        if data:
            return self._to_result(data, Decimal("0.40"))

        return None

    def extract_json_ld(self, html_bytes: bytes) -> dict | None:
        soup = BeautifulSoup(html_bytes, "html.parser")
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            raw = script.string or script.text or ""
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            candidates = parsed if isinstance(parsed, list) else [parsed]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                if (candidate.get("@type") or "").lower() != "product":
                    continue
                offers = candidate.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = offers.get("price")
                if price is None:
                    continue
                return {
                    "title": candidate.get("name") or "",
                    "price": str(price),
                    "currency": (offers.get("priceCurrency") or "PKR").upper(),
                    "availability": self.parse_schema_availability(str(offers.get("availability") or "")),
                    "images": self.extract_images(candidate.get("image")),
                    "description": candidate.get("description"),
                }
        return None

    def extract_opengraph(self, html_bytes: bytes) -> dict | None:
        soup = BeautifulSoup(html_bytes, "html.parser")
        og = {}
        for tag in soup.find_all("meta"):
            key = tag.get("property") or tag.get("name")
            if not key:
                continue
            og[key.lower()] = tag.get("content")

        title = og.get("og:title")
        price = og.get("og:price:amount")
        if not title or not price:
            return None

        return {
            "title": title,
            "price": price,
            "currency": (og.get("og:price:currency") or "PKR").upper(),
            "availability": self.parse_schema_availability(og.get("og:availability") or ""),
            "images": [og.get("og:image")] if og.get("og:image") else [],
            "description": og.get("description"),
        }

    def extract_meta_tags(self, html_bytes: bytes) -> dict | None:
        soup = BeautifulSoup(html_bytes, "html.parser")
        title = (soup.title.string.strip() if soup.title and soup.title.string else "")
        description = ""
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag:
            description = desc_tag.get("content") or ""

        combined = f"{title} {description}"
        price_match = re.search(r"(?:PKR|Rs\.?|Rs)\s*([\d,]+(?:\.\d{1,2})?)", combined, flags=re.IGNORECASE)
        if not title or not price_match:
            return None

        return {
            "title": title,
            "price": price_match.group(1).replace(",", ""),
            "currency": "PKR",
            "availability": "unknown",
            "images": [],
            "description": description or None,
        }

    def parse_schema_availability(self, avail_str: str) -> str:
        s = (avail_str or "").lower()
        if "instock" in s:
            return "in_stock"
        if "outofstock" in s or "discontinued" in s:
            return "out_of_stock"
        if "preorder" in s or "limitedavailability" in s:
            return "limited"
        return "unknown"

    def extract_images(self, image_data) -> list[str]:
        if isinstance(image_data, str):
            return [image_data]
        if isinstance(image_data, list):
            out: list[str] = []
            for item in image_data:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict) and isinstance(item.get("url"), str):
                    out.append(item["url"])
            return out
        if isinstance(image_data, dict) and isinstance(image_data.get("url"), str):
            return [image_data["url"]]
        return []

    def _to_result(self, data: dict, confidence: Decimal) -> HtmlScrapeResult:
        return HtmlScrapeResult(
            title=(data.get("title") or "").strip(),
            price=Decimal(str(data.get("price") or 0)),
            currency=(data.get("currency") or "PKR").upper(),
            availability=data.get("availability") or "unknown",
            images=data.get("images") or [],
            description=data.get("description"),
            confidence=confidence,
        )
