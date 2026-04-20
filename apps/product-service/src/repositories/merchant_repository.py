from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import Merchant


class MerchantRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_domain(self, domain: str) -> Merchant | None:
        return await self.db.scalar(select(Merchant).where(Merchant.domain == domain, Merchant.deleted_at.is_(None)))

    async def get_or_create(self, domain: str, platform: str) -> tuple[Merchant, bool]:
        from src.config import settings
        if settings.DATABASE_DIALECT == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(Merchant).values(
                name=domain,
                normalized_name=domain,
                domain=domain,
                platform_type=platform,
            ).on_conflict_do_update(
                index_elements=["domain"],
                set_={"platform_type": platform}
            ).returning(Merchant)
            
            res = await self.db.execute(stmt)
            merchant = res.scalar_one()
            return merchant, False  # returning False as we don't track newness easily with returning but it's safe
        
        # Fallback for SQLite/Tests
        existing = await self.find_by_domain(domain)
        if existing is not None:
            if platform and existing.platform_type != platform:
                existing.platform_type = platform
                await self.db.flush()
            return existing, False

        merchant = Merchant(
            name=domain,
            normalized_name=domain,
            domain=domain,
            platform_type=platform,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(merchant)
                await self.db.flush()
            return merchant, True
        except IntegrityError:
            existing = await self.find_by_domain(domain)
            if existing is None:
                raise
            return existing, False

    async def find_by_uuid(self, merchant_uuid: str) -> Merchant | None:
        return await self.db.scalar(select(Merchant).where(Merchant.uuid == merchant_uuid, Merchant.deleted_at.is_(None)))

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[Merchant]:
        rows = await self.db.scalars(
            select(Merchant)
            .where(Merchant.deleted_at.is_(None))
            .order_by(Merchant.name)
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    async def update(self, merchant: Merchant, **fields) -> Merchant:
        for key, value in fields.items():
            setattr(merchant, key, value)
        await self.db.flush()
        return merchant
