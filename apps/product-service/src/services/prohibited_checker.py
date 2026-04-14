from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import ProhibitedCategory, ProhibitedItemLog


@dataclass(slots=True)
class ProhibitedDecision:
    is_prohibited: bool
    category: str | None = None
    keyword: str | None = None


class ProhibitedCheckerService:
    async def check_text(
        self,
        db: AsyncSession,
        text: str,
        raw_url: str,
        canonical_url: str,
        user_id: int | None = None,
        product_id: int | None = None,
    ) -> ProhibitedDecision:
        normalized = text.lower()
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
                    return ProhibitedDecision(is_prohibited=True, category=category.category_name, keyword=keyword)

        return ProhibitedDecision(is_prohibited=False)
