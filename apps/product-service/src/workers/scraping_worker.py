from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName, RedisNS, RedisTTL
from sk_shared.models.product import Product, ScrapingJob
from sk_shared.redis_client import RedisClient

from src.services.extraction_waterfall import ExtractionWaterfallService


class ScrapingWorker:
    def __init__(self, db: AsyncSession, redis: RedisClient, concurrency: int = 1) -> None:
        self.db = db
        self.redis = redis
        self.concurrency = concurrency
        self.running = True

    async def run(self) -> None:
        while self.running:
            job = await self.redis.redis.brpop(QueueName.SCRAPING, timeout=5)
            if job is None:
                await asyncio.sleep(0)
                continue

            payload = json.loads(job[1].decode("utf-8"))
            await self._process(payload)

    async def _process(self, payload: dict) -> None:
        scraping_job = await self.db.scalar(select(ScrapingJob).where(ScrapingJob.uuid == UUID(payload["job_id"])))
        if scraping_job is None:
            return
        if scraping_job.status in {"completed", "failed"}:
            return

        scraping_job.status = "running"
        scraping_job.started_at = datetime.now(timezone.utc)
        await self.db.flush()

        service = ExtractionWaterfallService()
        result = await service.run_tier3(payload["canonical_url"], payload.get("platform", "CUSTOM"))
        if result.status != "completed":
            scraping_job.error_code = result.error_code
            scraping_job.error_message = result.error_message
            scraping_job.completed_at = datetime.now(timezone.utc)

            if scraping_job.attempt_number < scraping_job.max_attempts:
                scraping_job.attempt_number += 1
                scraping_job.status = "retrying"
                await self.db.commit()
                await self.redis.rpush(QueueName.SCRAPING, json.dumps(payload))
                return

            scraping_job.status = "failed"
            scraping_job.error_code = result.error_code
            scraping_job.error_message = result.error_message
            await self.db.commit()
            return

        product = Product(
            name=result.title,
            url=payload["input_url"],
            canonical_url=payload["canonical_url"],
            platform=payload.get("platform", "CUSTOM"),
            currency="PKR",
            cost_price=result.price,
            sale_price=result.price,
            stock_status="in_stock",
            in_stock=True,
            primary_image_s3=result.image_url,
            extraction_method=result.method,
            extraction_confidence=result.confidence,
        )
        self.db.add(product)
        await self.db.flush()

        scraping_job.product_id = product.id
        scraping_job.status = "completed"
        scraping_job.result = {
            "product_uuid": str(product.uuid),
            "title": result.title,
            "price": str(result.price),
            "method": result.method,
            "confidence": str(result.confidence),
        }
        scraping_job.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        await self.redis.set_json(
            f"{RedisNS.PRODUCT_UPO}:{product.uuid}",
            {
                "product_id": str(product.uuid),
                "source_url": product.canonical_url or product.url,
                "platform": product.platform,
                "extraction_method": product.extraction_method,
                "extraction_confidence": str(product.extraction_confidence),
                "availability": product.stock_status,
                "is_purchasable": bool(product.in_stock and not product.is_prohibited),
                "meta": {
                    "title": product.name,
                    "brand": None,
                    "description": None,
                    "images": [product.primary_image_s3] if product.primary_image_s3 else [],
                },
                "pricing": {
                    "amount": str(product.cost_price),
                    "currency": product.currency,
                },
            },
            ttl=RedisTTL.PRODUCT_CACHE,
        )
