from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.product import ScrapingJob


class ScrapingJobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_uuid(self, job_uuid):
        return await self.db.scalar(select(ScrapingJob).where(ScrapingJob.uuid == job_uuid))

    async def find_active_by_canonical_url(self, canonical_url: str) -> ScrapingJob | None:
        return await self.db.scalar(
            select(ScrapingJob)
            .where(
                ScrapingJob.canonical_url == canonical_url,
                ScrapingJob.status.in_(["queued", "running", "retrying"]),
            )
            .order_by(desc(ScrapingJob.created_at))
        )

    async def create_queued(
        self,
        *,
        order_id: int | None,
        user_id: int | None,
        input_url: str,
        canonical_url: str,
        platform_detected: str,
    ) -> ScrapingJob:
        job = ScrapingJob(
            order_id=order_id,
            user_id=user_id,
            input_url=input_url,
            canonical_url=canonical_url,
            platform_detected=platform_detected,
            status="queued",
            queued_at=datetime.now(timezone.utc),
        )
        self.db.add(job)
        await self.db.flush()
        return job
    async def find_active_by_product_id(self, product_id: int) -> ScrapingJob | None:
        return await self.db.scalar(
            select(ScrapingJob)
            .where(
                ScrapingJob.product_id == product_id,
                ScrapingJob.status.in_(["queued", "running", "retrying"]),
            )
            .order_by(desc(ScrapingJob.created_at))
        )

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[ScrapingJob]:
        rows = await self.db.scalars(
            select(ScrapingJob).order_by(desc(ScrapingJob.created_at)).limit(limit).offset(offset)
        )
        return list(rows)

    async def list_by_product(self, product_id: int, limit: int = 50, offset: int = 0) -> list[ScrapingJob]:
        rows = await self.db.scalars(
            select(ScrapingJob)
            .where(ScrapingJob.product_id == product_id)
            .order_by(desc(ScrapingJob.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(rows)
