from __future__ import annotations

from dataclasses import dataclass
import hashlib
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import ProhibitedCategory, ProhibitedItemLog
from sk_shared.redis_client import RedisClient
from src.config import settings


@dataclass(slots=True)
class ProhibitedDecision:
    is_prohibited: bool
    category: str | None = None
    keyword: str | None = None
    confidence: float = 0.0


class ProhibitedCheckerService:
    async def check_text(
        self,
        db: AsyncSession,
        text: str,
        raw_url: str,
        canonical_url: str,
        description: str | None = None,
        brand: str | None = None,
        redis: RedisClient | None = None,
        user_id: int | None = None,
        product_id: int | None = None,
    ) -> ProhibitedDecision:
        cache_key = self._negative_cache_key(canonical_url)
        if redis is not None and await redis.get(cache_key) == "0":
            return ProhibitedDecision(is_prohibited=False, confidence=0.0)

        normalized = " ".join([text or "", description or "", brand or ""]).lower()
        categories = await db.scalars(select(ProhibitedCategory))

        for category in categories:
            for keyword in category.keywords:
                if keyword.lower() in normalized:
                    db.add(
                        ProhibitedItemLog(
                            user_id=user_id,
                            product_id=product_id,
                            raw_url=raw_url,
                            canonical_url=canonical_url,
                            detected_category=category.category_name,
                            detected_keyword=keyword,
                            decision_reason="Matched prohibited keyword in product extraction",
                        )
                    )
                    await db.flush()
                    return ProhibitedDecision(is_prohibited=True, category=category.category_name, keyword=keyword, confidence=1.0)

        url_decision = await self.check_url(db=db, canonical_url=canonical_url)
        if url_decision.is_prohibited:
            return url_decision

        if redis is not None:
            await redis.set(cache_key, "0", ttl=3600)
        
        category = self.classify_category(normalized)
        return ProhibitedDecision(is_prohibited=False, category=category, confidence=0.7)

    def classify_category(self, text: str) -> str:
        """Heuristic-based positive categorization for Shariah monitoring."""
        mapping = settings.SHARIAH_CATEGORY_MAPPING
        for cat, keywords in mapping.items():
            if any(kw in text for kw in keywords):
                return cat
        return "Miscellaneous"

    async def check_url(self, db: AsyncSession, canonical_url: str) -> ProhibitedDecision:
        parsed = urlparse(canonical_url)
        domain = (parsed.netloc or "").lower().replace("www.", "")

        # Preferred path: query dedicated table if present in the shared schema.
        try:
            row = await db.execute(
                text("SELECT domain FROM prohibited_merchant_domains WHERE lower(domain) = :domain LIMIT 1"),
                {"domain": domain},
            )
            match = row.first()
            if match:
                return ProhibitedDecision(is_prohibited=True, category="ProhibitedMerchant", keyword=domain, confidence=0.8)
        except Exception:
            # Table may not exist yet in older environments.
            pass

        # Compatibility fallback when the dedicated table is unavailable.
        if domain in settings.SHARIAH_DOMAIN_DENYLIST:
            return ProhibitedDecision(is_prohibited=True, category="ProhibitedMerchant", keyword=domain, confidence=0.8)
        return ProhibitedDecision(is_prohibited=False, confidence=0.0)

    def _negative_cache_key(self, canonical_url: str) -> str:
        digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        return f"sk:prohibited:negative:{digest}"
