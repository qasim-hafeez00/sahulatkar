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
    # MEDIUM fix: negative-result caching could mask a category added to the
    # prohibited list within the cache window (an admin adds a new
    # ProhibitedCategory/keyword, but a URL cached as "not prohibited" up to
    # an hour earlier would keep sailing through unchecked). Two
    # complementary mitigations:
    #  1) A much shorter TTL (5 min instead of 1h) bounds the worst case even
    #     if invalidation below is ever missed.
    #  2) A catalog version counter (bumped by `invalidate_cache()` whenever
    #     the prohibited list changes — see admin.py's
    #     upsert/delete/sync-prohibited-category endpoints) is folded into
    #     the cache key, so any list change immediately invalidates every
    #     previously-cached negative result without needing to enumerate or
    #     SCAN individual per-URL keys.
    NEGATIVE_CACHE_TTL_SECONDS = 300
    _CATALOG_VERSION_KEY = "sk:prohibited:catalog_version"

    @classmethod
    async def invalidate_cache(cls, redis: RedisClient | None) -> None:
        """Bump the catalog version so every previously-cached negative
        result (keyed on the old version) is treated as a cache miss.

        Call this after any change to ProhibitedCategory rows or the
        prohibited-merchant-domains table (admin create/update/delete/sync).
        """
        if redis is None:
            return
        await redis.incr(cls._CATALOG_VERSION_KEY)

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
        cache_key = await self._negative_cache_key(canonical_url, redis)
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
            await redis.set(cache_key, "0", ttl=self.NEGATIVE_CACHE_TTL_SECONDS)
        
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

        try:
            # BUG FIX (found running the real order flow against real
            # Postgres): this raw-SQL check is best-effort by design (the
            # bare except below), but a failed statement inside an open
            # Postgres transaction poisons EVERY subsequent statement on
            # that same connection with `InFailedSQLTransactionError:
            # current transaction is aborted` until something rolls it
            # back -- the bare `except: pass` here never did, so the very
            # next query in this same request (the ProhibitedCategory
            # keyword check below) always failed too, surfacing as an
            # uncaught 500 on every `POST /products/extract` call. SQLite
            # (this repo's unit-test backend) has no equivalent semantics,
            # so no test ever caught this. A SAVEPOINT scopes the failure
            # to just this optional check -- `begin_nested()`'s own
            # rollback-on-exception undoes only the savepoint, leaving the
            # outer transaction (and every subsequent query on it) healthy,
            # regardless of whether the underlying cause is a missing
            # table, a transient connection issue, or anything else this
            # deliberately broad except is meant to tolerate.
            async with db.begin_nested():
                row = await db.execute(
                    text("SELECT domain FROM prohibited_merchant_domains WHERE lower(domain) = :domain LIMIT 1"),
                    {"domain": domain},
                )
                match = row.first()
            if match:
                return ProhibitedDecision(is_prohibited=True, category="ProhibitedMerchant", keyword=domain, confidence=0.8)
        except Exception:
            pass

        if domain in settings.SHARIAH_DOMAIN_DENYLIST:
            return ProhibitedDecision(is_prohibited=True, category="ProhibitedMerchant", keyword=domain, confidence=0.8)

        # Check full URL against ProhibitedCategory keywords
        categories = await db.scalars(select(ProhibitedCategory))
        canonical_url_lower = canonical_url.lower()
        for category in categories:
            for keyword in category.keywords:
                if keyword.lower() in canonical_url_lower:
                    return ProhibitedDecision(is_prohibited=True, category=category.category_name, keyword=keyword, confidence=0.9)

        return ProhibitedDecision(is_prohibited=False, confidence=0.0)

    async def _negative_cache_key(self, canonical_url: str, redis: RedisClient | None) -> str:
        digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        version = "0"
        if redis is not None:
            version = await redis.get(self._CATALOG_VERSION_KEY) or "0"
        return f"sk:prohibited:negative:v{version}:{digest}"
