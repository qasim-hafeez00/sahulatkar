from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient
from src.config import settings


class ProductCacheService:
    @staticmethod
    def _url_key(canonical_url: str) -> str:
        digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        return f"{RedisNS.PRODUCT_URL}:{digest}"

    @staticmethod
    def _upo_key(product_uuid: str) -> str:
        return f"{RedisNS.PRODUCT_UPO}:{product_uuid}"

    @staticmethod
    def _job_key(job_uuid: str) -> str:
        return f"sk:job:status:{job_uuid}"

    async def get_by_url(self, redis: RedisClient, db: AsyncSession, canonical_url: str) -> Product | None:
        cached_uuid = await redis.get(self._url_key(canonical_url))
        if not cached_uuid:
            return None
        try:
            product_uuid = UUID(cached_uuid)
        except Exception:
            return None
        return await db.scalar(select(Product).where(Product.uuid == product_uuid, Product.deleted_at.is_(None)))

    async def set_by_url(self, redis: RedisClient, canonical_url: str, product_uuid: str) -> None:
        await redis.set(self._url_key(canonical_url), product_uuid, ttl=settings.PRODUCT_CACHE_TTL_SECONDS)

    async def get_upo(self, redis: RedisClient, product_uuid: str) -> dict | None:
        return await redis.get_json(self._upo_key(product_uuid))

    async def set_upo(self, redis: RedisClient, product_uuid: str, upo_dict: dict) -> None:
        await redis.set_json(self._upo_key(product_uuid), upo_dict, ttl=settings.PRODUCT_CACHE_TTL_SECONDS)

    async def invalidate(self, redis: RedisClient, product_uuid: str, canonical_url: str) -> None:
        await redis.delete(self._url_key(canonical_url))
        await redis.delete(self._upo_key(product_uuid))

    async def get_job_status(self, redis: RedisClient, job_uuid: str) -> str | None:
        return await redis.get(self._job_key(job_uuid))

    async def set_job_status(self, redis: RedisClient, job_uuid: str, status: str) -> None:
        await redis.set(self._job_key(job_uuid), status, ttl=24 * 3600)
