from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import ProhibitedCategory


class ProhibitedCategoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[ProhibitedCategory]:
        rows = await self.db.scalars(select(ProhibitedCategory).order_by(ProhibitedCategory.category_name.asc()))
        return list(rows)

    async def find_by_name(self, category_name: str) -> ProhibitedCategory | None:
        return await self.db.scalar(
            select(ProhibitedCategory).where(ProhibitedCategory.category_name == category_name)
        )

    async def upsert(self, category_name: str, keywords: list[str], shariah_basis: str | None = None) -> tuple[ProhibitedCategory, bool]:
        existing = await self.find_by_name(category_name)
        if existing is not None:
            existing.keywords = sorted(set((existing.keywords or []) + keywords))
            if shariah_basis is not None:
                existing.shariah_basis = shariah_basis
            await self.db.flush()
            return existing, False

        row = ProhibitedCategory(
            category_name=category_name,
            keywords=keywords,
            shariah_basis=shariah_basis,
        )
        self.db.add(row)
        await self.db.flush()
        return row, True

    async def delete(self, category_id: int) -> bool:
        row = await self.db.scalar(select(ProhibitedCategory).where(ProhibitedCategory.id == category_id))
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True
