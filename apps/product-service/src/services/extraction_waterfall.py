from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from src.config import settings


@dataclass(slots=True)
class ExtractionResult:
    status: str
    method: str
    confidence: Decimal
    title: str
    price: Decimal
    image_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ExtractionWaterfallService:
    async def extract(self, canonical_url: str, platform: str) -> ExtractionResult:
        tier1 = await self._tier1_rye(canonical_url, platform)
        if tier1 is not None:
            return tier1

        tier2 = await self._tier2_jsonld(canonical_url)
        if tier2 is not None:
            return tier2

        # Tier 3 can be long-running, so API can decide to enqueue this request.
        return ExtractionResult(
            status="extracting",
            method="playwright_llm",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
        )

    async def run_tier3(self, canonical_url: str, platform: str) -> ExtractionResult:
        if not settings.FEATURE_GROQ_ENABLED and not settings.FEATURE_OPENAI_FALLBACK:
            return ExtractionResult(
                status="failed",
                method="playwright_llm",
                confidence=Decimal("0.000"),
                title="",
                price=Decimal("0.00"),
                error_code="EXTRACTION_FAILED",
                error_message="Tier3 providers are disabled",
            )

        from src.extractors.playwright_agent import PlaywrightExtractionAgent
        agent = PlaywrightExtractionAgent()
        
        try:
            data = await agent.extract(canonical_url)
            return ExtractionResult(
                status="completed",
                method="playwright_llm",
                confidence=Decimal("0.850"),
                title=data.get("title", "Unknown Product"),
                price=Decimal(str(data.get("price", 0))),
                image_url=data.get("image_url"),
            )
        except Exception as e:
            return ExtractionResult(
                status="failed",
                method="playwright_llm",
                confidence=Decimal("0.000"),
                title="",
                price=Decimal("0.00"),
                error_code="EXTRACTION_ERROR",
                error_message=str(e),
            )

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
