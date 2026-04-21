from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import Product


class ProductLifecycleService:
    """Proxy lifecycle semantics using current product fields.

    Shared ProductStatus enum is not yet available in sk_shared for this repo,
    so we map lifecycle intentions onto existing fields.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def mark_prohibited(self, product: Product, reason: str) -> Product:
        product.is_prohibited = True
        product.prohibition_reason = reason
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def unmark_prohibited(self, product: Product) -> Product:
        product.is_prohibited = False
        product.prohibition_reason = None
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def soft_delete(self, product: Product) -> Product:
        product.deleted_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def mark_stale(self, product: Product) -> Product:
        product.status = "stale"
        await self.db.commit()
        await self.db.refresh(product)
        return product
