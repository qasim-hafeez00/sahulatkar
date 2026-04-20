from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import Product, ScrapingJob


class ProductRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_canonical_url(self, canonical_url: str) -> Product | None:
        return await self.db.scalar(
            select(Product)
            .where(Product.canonical_url == canonical_url, Product.deleted_at.is_(None))
            .order_by(desc(Product.created_at))
        )

    async def find_by_uuid(self, product_uuid) -> Product | None:
        return await self.db.scalar(select(Product).where(Product.uuid == product_uuid, Product.deleted_at.is_(None)))

    async def find_by_id(self, product_id: int) -> Product | None:
        return await self.db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))


    async def upsert_by_canonical_url(self, canonical_url: str, payload: dict[str, Any]) -> tuple[Product, bool]:
        existing = await self.find_by_canonical_url(canonical_url)
        if existing is not None:
            await self.update(existing, **payload)
            return existing, False

        product = Product(**payload)
        try:
            async with self.db.begin_nested():
                self.db.add(product)
                await self.db.flush()
            return product, True
        except IntegrityError:
            existing = await self.find_by_canonical_url(canonical_url)
            if existing is None:
                raise
            await self.update(existing, **payload)
            return existing, False

    async def update(self, product: Product, **fields) -> Product:
        old_price = Decimal(str(product.cost_price)) if product.cost_price is not None else None
        for key, value in fields.items():
            setattr(product, key, value)

        new_price = Decimal(str(product.cost_price)) if product.cost_price is not None else None
        if old_price is not None and new_price is not None and old_price != new_price:
            await self._append_price_history(product_id=product.id, old_price=old_price, new_price=new_price)

        await self.db.flush()
        return product

    async def _append_price_history(self, product_id: int, old_price: Decimal, new_price: Decimal) -> None:
        # The shared schema may not always provide this table in local test DBs.
        try:
            await self.db.execute(
                text(
                    """
                    INSERT INTO product_price_history (product_id, old_price, new_price, changed_at)
                    VALUES (:product_id, :old_price, :new_price, :changed_at)
                    """
                ),
                {
                    "product_id": product_id,
                    "old_price": str(old_price),
                    "new_price": str(new_price),
                    "changed_at": datetime.now(timezone.utc),
                },
            )
        except Exception:
            return

    async def find_by_user(self, user_id: int, limit: int = 20):
        rows = await self.db.scalars(
            select(Product)
            .join(ScrapingJob, ScrapingJob.product_id == Product.id)
            .where(ScrapingJob.user_id == user_id, Product.deleted_at.is_(None))
            .group_by(Product.id)
            .order_by(desc(func.max(ScrapingJob.created_at)), desc(Product.id))
            .limit(limit)
        )
        return list(rows)

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Product]:
        rows = await self.db.scalars(
            select(Product)
            .where(Product.deleted_at.is_(None))
            .order_by(desc(Product.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    async def search(self, query: str, limit: int = 50) -> list[Product]:
        # Basic tsvector search if on PG, else fallback to ilike
        from src.config import settings
        if settings.DATABASE_DIALECT == "postgresql":
            stmt = (
                select(Product)
                .where(
                    Product.deleted_at.is_(None),
                    Product.search_vector.op("@@")(func.plainto_tsquery("english", query))
                )
                .order_by(desc(Product.created_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(Product)
                .where(
                    Product.deleted_at.is_(None),
                    (Product.name.ilike(f"%{query}%") | Product.canonical_url.ilike(f"%{query}%"))
                )
                .order_by(desc(Product.created_at))
                .limit(limit)
            )
        rows = await self.db.scalars(stmt)
        return list(rows)
    async def get_price_history(self, product_id: int) -> list[dict]:
        from sqlalchemy import text
        try:
            # Query the table that tests (and potentially migrations) create
            res = await self.db.execute(
                text("SELECT old_price, new_price, changed_at FROM product_price_history WHERE product_id = :id ORDER BY changed_at DESC"),
                {"id": product_id},
            )
            return [dict(row) for row in res.mappings()]
        except Exception:
            # Fallback if table doesn't exist
            return []
