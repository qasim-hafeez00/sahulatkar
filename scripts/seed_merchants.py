"""
Seeds merchant rows with tuned `scrape_config` overrides for the real
merchant sites the platform targets first (see docs/plan.md M03 and the
web-customer completion plan). `scrape_config` was previously an unused
column — apps/product-service/src/extractors/playwright_agent.py now reads
`wait_selector` / `content_selector` from it (falling back to the existing
hardcoded per-platform heuristics when absent), so seeding it here actually
changes Tier 3 extraction behavior for these domains.

Selectors are only seeded where they're safe to be wrong: `wait_selector`
mirrors the same class the code already assumed hardcoded for Daraz before
this change, so this doesn't introduce a new unverified guess. Validate
against the live site (docs/plan.md M03 test note: "golden URLs per
platform") before trusting it further, and tune from there.

Run: python scripts/seed_merchants.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("packages/shared-python"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sk_admin:localdev123@localhost:5434/sahulatkar")

# platform_type / bot_detection_level reflect the tiers already assigned in
# extraction_waterfall.py's per-platform tier ordering — kept in sync here so
# admin tooling reading this table shows an accurate picture, not just the
# scrape_config override.
MERCHANTS = [
    {
        "name": "Daraz Pakistan",
        "domain": "daraz.pk",
        "platform_type": "DARAZ",
        "bot_detection_level": "medium",
        "has_captcha": False,
        "scrape_config": {"wait_selector": ".pdp-product-title"},
    },
    {
        "name": "AliExpress",
        "domain": "aliexpress.com",
        "platform_type": "ALIEXPRESS",
        "bot_detection_level": "high",
        "has_captcha": True,
        "captcha_type": "slider",
        # No proxy budget for MVP (free-tier decision) — expect a higher
        # block/CAPTCHA rate here than Daraz; failures fall through to HITL.
        "scrape_config": None,
    },
]


async def seed_merchants() -> None:
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        for m in MERCHANTS:
            await conn.execute(
                text("""
                    INSERT INTO merchants
                        (name, domain, platform_type, bot_detection_level, has_captcha, captcha_type, scrape_config, status, is_active, uuid, created_at, updated_at)
                    VALUES
                        (:name, :domain, :platform_type, :bot_detection_level, :has_captcha, :captcha_type, :scrape_config, 'active', true, gen_random_uuid(), now(), now())
                    ON CONFLICT (domain) DO UPDATE SET
                        scrape_config = EXCLUDED.scrape_config,
                        bot_detection_level = EXCLUDED.bot_detection_level,
                        has_captcha = EXCLUDED.has_captcha,
                        captcha_type = EXCLUDED.captcha_type,
                        updated_at = now();
                """),
                {
                    "name": m["name"],
                    "domain": m["domain"],
                    "platform_type": m["platform_type"],
                    "bot_detection_level": m["bot_detection_level"],
                    "has_captcha": m["has_captcha"],
                    "captcha_type": m.get("captcha_type"),
                    "scrape_config": None if m["scrape_config"] is None else json.dumps(m["scrape_config"]),
                },
            )
    await engine.dispose()
    print(f"Seeded {len(MERCHANTS)} merchants.")


if __name__ == "__main__":
    asyncio.run(seed_merchants())
