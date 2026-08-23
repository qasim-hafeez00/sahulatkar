import dataclasses
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from src.config import settings
from src.extractors.html_scraper import HtmlScraper
from src.extractors.rye_client import RyeClient
from src.extractors.violet_client import VioletClient
from sk_shared.redis_client import RedisClient
from src.middleware.metrics import EXTRACTION_LATENCY, EXTRACT_RATE_LIMIT_HITS


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
    description: str | None = None
    brand: str | None = None
    images: list[str] = field(default_factory=list)
    variants: list[dict] = field(default_factory=list)
    extraction_confidence: Decimal | None = None
    debug_screenshot_b64: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ExtractionWaterfallService:
    def __init__(self, redis: RedisClient | None = None) -> None:
        self.redis = redis
        self._html_scraper = HtmlScraper()
        self._rye_client = RyeClient(api_key=settings.RYE_API_KEY, base_url=settings.RYE_API_URL)
        self._violet_client = VioletClient(api_key=settings.VIOLET_API_KEY, base_url=settings.VIOLET_API_URL)

    async def _check_circuit_breaker(self, tier_name: str, domain: str | None = None) -> bool:
        """Check if a tier or domain is currently blocked.
        """
        if not self.redis:
            return False
        
        # Check global tier block
        if await self.redis.get(f"sk:cb:blocked:{tier_name}"):
            EXTRACT_RATE_LIMIT_HITS.labels(tier=tier_name, domain="all").inc()
            return True
            
        # Check domain-specific block within this tier
        if domain and await self.redis.get(f"sk:cb:blocked:{tier_name}:{domain}"):
            EXTRACT_RATE_LIMIT_HITS.labels(tier=tier_name, domain=domain).inc()
            return True
            
        return False

    async def _trip_circuit_breaker(self, tier_name: str, domain: str | None = None):
        """Trip circuit breaker for a specific tier/domain."""
        if not self.redis:
            return
            
        suffix = f":{domain}" if domain else ""
        key = f"sk:cb:failures:{tier_name}{suffix}"
        
        val = await self.redis.redis.incr(key)
        if val == 1:
            await self.redis.redis.expire(key, 60)
            
        if val >= 5:
            # Block for 5 minutes (domain block) or 2 minutes (tier block)
            ttl = 300 if domain else 120
            await self.redis.set(f"sk:cb:blocked:{tier_name}{suffix}", "1", ttl=ttl)
            await self.redis.delete(key)

    async def _reset_circuit_breaker(self, tier_name: str, domain: str | None = None) -> None:
        if not self.redis:
            return
        suffix = f":{domain}" if domain else ""
        await self.redis.delete(f"sk:cb:failures:{tier_name}{suffix}")

    def _validate_extraction(self, result: ExtractionResult) -> ExtractionResult:
        if result.status != "completed":
            return result
        
        if not result.title or len(result.title.strip()) < 3:
            return dataclasses.replace(result, status="failed", error_code="EMPTY_TITLE", error_message="Extracted title is too short or empty")
        
        if result.price <= Decimal("0"):
            return dataclasses.replace(result, status="failed", error_code="INVALID_PRICE", error_message="Extracted price must be greater than zero")

        if result.price < settings.MIN_PRODUCT_PRICE_PKR or result.price > settings.MAX_PRODUCT_PRICE_PKR:
            return dataclasses.replace(
                result,
                status="failed",
                error_code="PRICE_OUT_OF_RANGE",
                error_message="Extracted price is outside allowed financing range",
            )
            
        return result

    def _threshold_for_tier(self, tier: str) -> Decimal:
        base = Decimal(str(settings.EXTRACTION_CONFIDENCE_THRESHOLD))
        # Earlier tiers should maintain stricter confidence gates.
        defaults = {
            "tier1": Decimal("0.90"),
            "tier2a": Decimal("0.80"),
            "tier2b": Decimal("0.60"),
            "tier3": base,
        }
        tier_default = defaults.get(tier, base)
        # Respect runtime global threshold if it is stricter than tier default.
        return max(base, tier_default)

    async def extract(self, canonical_url: str, platform: str, scrape_config: dict | None = None) -> ExtractionResult:
        normalized_platform = (platform or "CUSTOM").upper()

        # Social-commerce storefronts (Instagram, etc.) have no structured
        # product page or checkout to automate — ordering happens via DM
        # negotiation with the seller. Every automated tier would just waste
        # an attempt, so route straight to manual/HITL fulfillment instead.
        if normalized_platform == "SOCIAL_COMMERCE":
            if settings.FEATURE_HITL_ESCALATION:
                return ExtractionResult(
                    status="hitl_required",
                    method="hitl",
                    confidence=Decimal("0.000"),
                    title="",
                    price=Decimal("0.00"),
                    error_code="SOCIAL_COMMERCE_MANUAL_ONLY",
                    error_message="This is a social-commerce storefront — our team will purchase this manually.",
                )
            return ExtractionResult(
                status="failed",
                method="waterfall",
                confidence=Decimal("0.000"),
                title="",
                price=Decimal("0.00"),
                error_code="SOCIAL_COMMERCE_MANUAL_ONLY",
                error_message="Social-commerce storefronts aren't supported for automated purchase.",
            )

        failures: list[str] = []
        # Best price seen from any earlier tier attempt (even one that didn't
        # meet its confidence threshold) — used to sanity-check Tier 3's
        # LLM-derived price before trusting it as the purchase cost basis.
        prior_price_hint: Decimal | None = None

        async def _run_tier(name: str, domain: str, fn):
            t0 = time.perf_counter()
            result = await fn()
            status = "failed" if result is None else result.status
            EXTRACTION_LATENCY.labels(tier=name, domain=domain, status=status).observe(time.perf_counter() - t0)
            return result

        async def _accept_or_none(tier_name: str, domain: str, result: ExtractionResult | None) -> ExtractionResult | None:
            nonlocal prior_price_hint
            if result is None:
                failures.append(f"{tier_name}:no_result")
                return None
            if result.status == "hitl_required":
                return result

            validated = self._validate_extraction(result)
            if validated.status != "completed":
                failures.append(f"{tier_name}:{validated.error_code or validated.status}")
                return None

            if tier_name == "tier3":
                if prior_price_hint is not None and prior_price_hint > 0:
                    drift_pct = abs(validated.price - prior_price_hint) / prior_price_hint * Decimal("100")
                    if drift_pct > settings.TIER3_PRICE_CROSSCHECK_TOLERANCE_PCT:
                        failures.append(
                            f"{tier_name}:price_crosscheck_failed:llm={validated.price}:prior={prior_price_hint}"
                        )
                        return None
            elif validated.price > 0:
                prior_price_hint = validated.price

            threshold = self._threshold_for_tier(tier_name)
            if validated.confidence < threshold:
                failures.append(f"{tier_name}:low_confidence:{validated.confidence}")
                return None
            await self._reset_circuit_breaker(tier_name, domain)
            return validated

        # DARAZ exclusion: We skip Tier1 (Rye) and Tier2A (Violet) for DARAZ 
        # because these aggregators do not reliably support the Daraz Pakistan DOM structure.
        if normalized_platform in {"WOOCOMMERCE", "BIGCOMMERCE", "MAGENTO"}:
            order = ["tier2a", "tier2b", "tier3"]
        elif normalized_platform == "DARAZ":
            order = ["tier2b", "tier3"]
        elif normalized_platform in {"AMAZON", "SHOPIFY"}:
            order = ["tier1", "tier2a", "tier2b", "tier3"]
        else:
            order = ["tier1", "tier2a", "tier2b", "tier3"]

        from urllib.parse import urlparse
        domain = urlparse(canonical_url).netloc.lower().replace("www.", "")

        for tier in order:
            if tier == "tier1":
                if await self._check_circuit_breaker("tier1", domain):
                    continue
                candidate = await _run_tier("tier1", domain, lambda: self._tier1_rye(canonical_url, platform))
                if candidate is None:
                    await self._trip_circuit_breaker("tier1", domain)
            elif tier == "tier2a":
                if await self._check_circuit_breaker("tier2a", domain):
                    continue
                candidate = await _run_tier("tier2a", domain, lambda: self._tier2a_violet(canonical_url))
                if candidate is None:
                    await self._trip_circuit_breaker("tier2a", domain)
            elif tier == "tier2b":
                candidate = await _run_tier("tier2b", domain, lambda: self._tier2b_html(canonical_url))
            else:
                candidate = await _run_tier("tier3", domain, lambda: self.run_tier3(canonical_url, platform, scrape_config))

            accepted = await _accept_or_none(tier, domain, candidate)
            if accepted is not None:
                return accepted

        if settings.FEATURE_HITL_ESCALATION:
            return ExtractionResult(
                status="hitl_required",
                method="hitl",
                confidence=Decimal("0.000"),
                title="",
                price=Decimal("0.00"),
                error_code="EXTRACTION_FAILED",
                error_message=f"All extraction tiers failed: {' | '.join(failures) if failures else 'unknown'}",
            )

        return ExtractionResult(
            status="failed",
            method="waterfall",
            confidence=Decimal("0.000"),
            title="",
            price=Decimal("0.00"),
            error_code="EXTRACTION_FAILED",
            error_message=f"All extraction tiers failed: {' | '.join(failures) if failures else 'unknown'}",
        )

    async def run_tier3(self, canonical_url: str, platform: str, scrape_config: dict | None = None) -> ExtractionResult:
        start_time = time.perf_counter()
        from urllib.parse import urlparse
        domain = urlparse(canonical_url).netloc.lower().replace("www.", "")

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
            EXTRACTION_LATENCY.labels(tier="tier3", domain=domain, status=res.status).observe(time.perf_counter() - start_time)
            return res

        from src.extractors.playwright_agent import PlaywrightExtractionAgent
        agent = PlaywrightExtractionAgent()

        try:
            data = await agent.extract(canonical_url, scrape_config=scrape_config)
            res = ExtractionResult(
                status="completed",
                method="playwright_llm",
                confidence=Decimal(str(data.get("confidence", "0.850"))),
                title=data.get("title", "Unknown Product"),
                price=Decimal(str(data.get("price", 0))),
                availability=data.get("availability", "in_stock"),
                ships_to_pakistan=data.get("ships_to_pakistan", True),
                image_url=data.get("image_url"),
                description=data.get("description"),
                brand=data.get("brand"),
                images=list(data.get("images") or ([data.get("image_url")] if data.get("image_url") else [])),
                variants=list(data.get("variants") or []),
                debug_screenshot_b64=data.get("debug_screenshot_b64"),
            )
            res = self._validate_extraction(res)
            EXTRACTION_LATENCY.labels(tier="tier3", domain=domain, status=res.status).observe(time.perf_counter() - start_time)
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
            EXTRACTION_LATENCY.labels(tier="tier3", domain=domain, status=res.status).observe(time.perf_counter() - start_time)
            return res

    async def _tier1_rye(self, canonical_url: str, platform: str) -> ExtractionResult | None:
        if not settings.FEATURE_RYE_ENABLED or not settings.RYE_API_KEY:
            return None

        try:
            data = await self._rye_client.fetch_product(canonical_url)
            if data is None:
                return None
            return ExtractionResult(
                status="completed",
                method="rye_api",
                confidence=Decimal("0.980"),
                title=data.title,
                price=data.price,
                availability=data.availability,
                image_url=(data.images[0] if data.images else None),
                description=getattr(data, "description", None),
                brand=getattr(data, "brand", None),
                images=list(getattr(data, "images", None) or []),
                variants=list(getattr(data, "variants", None) or []),
            )
        except Exception:
            return None

    async def _tier2a_violet(self, canonical_url: str) -> ExtractionResult | None:
        if not settings.FEATURE_VIOLET_ENABLED or not settings.VIOLET_API_KEY:
            return None
        data = await self._violet_client.fetch_product(canonical_url)
        if data is None:
            return None
        return ExtractionResult(
            status="completed",
            method="violet_api",
            confidence=Decimal("0.800"),
            title=data.title,
            price=data.price,
            availability=data.availability,
            image_url=(data.images[0] if data.images else None),
            description=getattr(data, "description", None),
            brand=getattr(data, "brand", None),
            images=list(getattr(data, "images", None) or []),
            variants=list(getattr(data, "variants", None) or []),
        )

    async def _tier2b_html(self, canonical_url: str) -> ExtractionResult | None:
        data = await self._html_scraper.fetch_and_parse(canonical_url)
        if data is None:
            return None
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=data.confidence,
            title=data.title,
            price=data.price,
            availability=data.availability,
            image_url=(data.images[0] if data.images else None),
            description=getattr(data, "description", None),
            brand=getattr(data, "brand", None),
            images=list(getattr(data, "images", None) or []),
            variants=list(getattr(data, "variants", None) or []),
        )

    async def _tier2_jsonld(self, canonical_url: str) -> ExtractionResult | None:
        # Backward-compatible alias for old tests.
        return await self._tier2b_html(canonical_url)

    async def _tier3_playwright(self, canonical_url: str, platform: str) -> ExtractionResult:
        return await self.run_tier3(canonical_url, platform)
