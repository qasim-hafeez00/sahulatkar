from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import Merchant, Product

from src.repositories.merchant_repository import MerchantRepository


class MerchantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.merchant_repo = MerchantRepository(db)

    async def get_or_create(self, domain: str, platform: str) -> Merchant:
        merchant, _ = await self.merchant_repo.get_or_create(domain=domain, platform=platform)
        return merchant

    async def block(self, domain: str, reason: str) -> tuple[Merchant, int]:
        merchant = await self.merchant_repo.find_by_domain(domain)
        if merchant is None:
            raise ValueError("MERCHANT_NOT_FOUND")

        merchant.status = "blocked"
        merchant.is_active = False

        products = await self.db.scalars(
            select(Product).where(Product.merchant_id == merchant.id, Product.deleted_at.is_(None))
        )
        affected = 0
        for product in products:
            product.is_prohibited = True
            product.prohibition_reason = reason
            affected += 1

        await self.db.commit()
        return merchant, affected
