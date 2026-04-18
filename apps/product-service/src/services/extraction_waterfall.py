import dataclasses
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from src.config import settings
from src.middleware.metrics import EXTRACTION_LATENCY


@dataclass(slots=True)
class ExtractionResult:
    status: str
    method: str
    confidence: Decimal
    title: str
    price: Decimal
    availability: Literal["in_stock", "out_of_stock", "limited", "unknown"] = "unknown"
    ships_to_pakistan: bool = True
    image_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ExtractionWaterfallService:
    def _validate_extraction(self, result: ExtractionResult) -> ExtractionResult:
        if result.status != "completed":
            return result
        
        if not result.title or len(result.title.strip()) < 3:
            return dataclasses.replace(result, status="failed", error_code="EMPTY_TITLE", error_message="Extracted title is too short or empty")
        
        if result.price <= Decimal("0"):
            return dataclasses.replace(result, status="failed", error_code="INVALID_PRICE", error_message="Extracted price must be greater than zero")
            
        return result

    async def extract(self, canonical_url: str, platform: str) -> ExtractionResult:
        start_time = time.perf_counter()
        
        # Tier 1: Rye
        tier1 = await self._tier1_rye(canonical_url, platform)
        if tier1 is not None:
            res = self._validate_extraction(tier1)
            EXTRACTION_LATENCY.labels(tier="tier1", status=res.status).observe(time.perf_counter() - start_time)
            if res.status == "completed":
                return res

        # Tier 2: JSON-LD
        tier2 = await self._tier2_jsonld(canonical_url)
        if tier2 is not None:
            res = self._validate_extraction(tier2)
            EXTRACTION_LATENCY.labels(tier="tier2", status=res.status).observe(time.perf_counter() - start_time)
            if res.status == "completed":
                return res

        # Tier 3 can be long-running, so API can decide to enqueue this request.
        # This part just says "we are enqueuing", no latency observation here as it's just a hand-off
        return ExtractionResult(
            status="extracting",
            method="playwright_llm",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
        )

    async def run_tier3(self, canonical_url: str, platform: str) -> ExtractionResult:
        start_time = time.perf_counter()
        
        if not settings.FEATURE_GROQ_ENABLED and not settings.FEATURE_OPENAI_FALLBACK:
            res = ExtractionResult(
                status="failed",
                method="playwright_llm",
                confidence=Decimal("0.000"),
                title="",
                price=Decimal("0.00"),
                error_code="EXTRACTION_FAILED",
                error_message="Tier3 providers are disabled",
            )
            EXTRACTION_LATENCY.labels(tier="tier3", status=res.status).observe(time.perf_counter() - start_time)
            return res

        from src.extractors.playwright_agent import PlaywrightExtractionAgent
        agent = PlaywrightExtractionAgent()
        
        try:
            data = await agent.extract(canonical_url)
            res = ExtractionResult(
                status="completed",
                method="playwright_llm",
                confidence=Decimal("0.850"),
                title=data.get("title", "Unknown Product"),
                price=Decimal(str(data.get("price", 0))),
                availability=data.get("availability", "in_stock"),
                ships_to_pakistan=data.get("ships_to_pakistan", True),
                image_url=data.get("image_url"),
            )
            res = self._validate_extraction(res)
            EXTRACTION_LATENCY.labels(tier="tier3", status=res.status).observe(time.perf_counter() - start_time)
            return res
        except Exception as e:
            res = ExtractionResult(
                status="failed",
                method="playwright_llm",
                confidence=Decimal("0.000"),
                title="",
                price=Decimal("0.00"),
                error_code="EXTRACTION_ERROR",
                error_message=str(e),
            )
            EXTRACTION_LATENCY.labels(tier="tier3", status=res.status).observe(time.perf_counter() - start_time)
            return res

    async def _tier1_rye(self, canonical_url: str, platform: str) -> ExtractionResult | None:
        if not settings.FEATURE_RYE_ENABLED or not settings.RYE_API_KEY:
            return None

        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{settings.RYE_API_URL}/products",
                    params={"url": canonical_url},
                    headers={"Authorization": f"Bearer {settings.RYE_API_KEY}", "Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    return None
                
                data = resp.json()
                # Assuming Rye returns a structure similar to our UPO
                price_data = data.get("price", {})
                amount = Decimal(str(price_data.get("amountSubunits", 0))) / Decimal("100")
                
                return ExtractionResult(
                    status="completed",
                    method="rye_api",
                    confidence=Decimal("0.980"),
                    title=data.get("name", "Unknown Product"),
                    price=amount,
                    image_url=data.get("images", [None])[0],
                )
        except Exception:
            return None

    async def _tier2_jsonld(self, canonical_url: str) -> ExtractionResult | None:
        import httpx
        from bs4 import BeautifulSoup
        import json
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(canonical_url, headers={"User-Agent": "Mozilla/5.0 SahulatKar-Bot/1.0"})
                if resp.status_code != 200:
                    return None
                
                soup = BeautifulSoup(resp.content, "html.parser")
                scripts = soup.find_all("script", type="application/ld+json")
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "Product":
                                name = item.get("name")
                                offers = item.get("offers", {})
                                if isinstance(offers, list):
                                    offers = offers[0] if offers else {}
                                price = offers.get("price")
                                if name and price:
                                    return ExtractionResult(
                                        status="completed",
                                        method="json_ld",
                                        confidence=Decimal("0.850"),
                                        title=name,
                                        price=Decimal(str(price)),
                                        image_url=item.get("image"),
                                    )
                    except (json.JSONDecodeError, TypeError):
                        continue
        except Exception:
            pass
        return None
