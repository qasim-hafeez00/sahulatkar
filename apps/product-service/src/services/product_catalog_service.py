from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import Product

from src.config import settings
from src.repositories.product_repository import ProductRepository


def _sanitize_text(value: str, max_len: int) -> str:
    cleaned = value.replace("\x00", "").strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


class ProductCatalogService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    async def patch_product(self, product: Product, **fields) -> Product:
        if "name" in fields and fields["name"] is not None:
            fields["name"] = _sanitize_text(str(fields["name"]), 255)
        if "url" in fields and fields["url"] is not None:
            fields["url"] = _sanitize_text(str(fields["url"]), 2048)
        if "canonical_url" in fields and fields["canonical_url"] is not None:
            fields["canonical_url"] = _sanitize_text(str(fields["canonical_url"]), 2048)

        for money_key in ("cost_price", "sale_price"):
            if money_key in fields and fields[money_key] is not None:
                fields[money_key] = Decimal(str(fields[money_key]))

        updated = await self.product_repo.update(product, **fields)

        if settings.DATABASE_DIALECT == "postgresql" and (
            "name" in fields or "canonical_url" in fields
        ):
            await self.db.execute(
                text(
                    """
                    UPDATE products
                    SET search_vector = to_tsvector('english', coalesce(name, '') || ' ' || coalesce(canonical_url, ''))
                    WHERE id = :id
                    """
                ),
                {"id": updated.id},
            )

        await self.db.commit()
        await self.db.refresh(updated)
        return updated
