from __future__ import annotations

import asyncio
import json
import logging
import signal
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from sk_shared.constants import QueueName
from sk_shared.database import SessionLocal
from sk_shared.models.product import Product, ScrapingJob
from sk_shared.redis_client import RedisClient, get_redis_client

from src.config import settings
from src.middleware.metrics import STALE_PRODUCTS_DETECTED

logger = logging.getLogger(__name__)
LOCK_KEY = "sk:lock:price_staleness_worker"
LOCK_TTL_SECONDS = 7200


class PriceStalenessWorker:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis
        self.running = True

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: setattr(self, "running", False))
        except NotImplementedError:
            pass

        while self.running:
            acquired = await self.redis.redis.set(LOCK_KEY, socket.gethostname(), ex=LOCK_TTL_SECONDS, nx=True)
            if acquired:
                try:
                    await self._run_once()
                    await self._expire_old_products()
                finally:
                    await self.redis.redis.delete(LOCK_KEY)
            await asyncio.sleep(settings.PRODUCT_STALENESS_CHECK_INTERVAL_SECONDS)

    async def _run_once(self) -> None:
        stale_threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.PRODUCT_STALE_AFTER_SECONDS)
        async with SessionLocal() as db:
            result = await db.execute(
                select(Product)
                .outerjoin(
                    ScrapingJob,
                    and_(
                        ScrapingJob.product_id == Product.id,
                        ScrapingJob.status.in_(["queued", "running", "retrying"]),
                    ),
                )
                .where(
                    Product.deleted_at.is_(None),
                    Product.is_prohibited.is_(False),
                    ScrapingJob.id.is_(None),
                    Product.updated_at < stale_threshold,
                )
                .limit(settings.PRODUCT_STALENESS_BATCH_SIZE)
            )
            products = list(result.scalars())

            if not products:
                return

            STALE_PRODUCTS_DETECTED.inc(len(products))
            now = datetime.now(timezone.utc)
            for product in products:
                product.status = "stale"
                job = ScrapingJob(
                    product_id=product.id,
                    input_url=product.url,
                    canonical_url=product.canonical_url,
                    platform_detected=product.platform or "CUSTOM",
                    status="queued",
                    # Same naive-vs-aware bug as scraping_worker.py's own
                    # queue_job path — queued_at is TIMESTAMP WITHOUT TIME
                    # ZONE. Unlike scraping_worker/checkout_consumer, this
                    # worker has no per-job try/except, so the unhandled
                    # DataError crashed the entire process outright rather
                    # than just failing one job.
                    queued_at=now.replace(tzinfo=None),
                )
                db.add(job)
                await db.flush()
                await self.redis.lpush(
                    QueueName.SCRAPING,
                    json.dumps(
                        {
                            "job_id": str(job.uuid),
                            "input_url": product.url,
                            "canonical_url": product.canonical_url,
                            "platform": product.platform or "CUSTOM",
                            "triggered_by": "price_staleness_worker",
                        }
                    ),
                )

            await db.commit()

    async def _expire_old_products(self) -> None:
        expiration_threshold = datetime.now(timezone.utc) - timedelta(days=30)
        async with SessionLocal() as db:
            from sk_shared.models.checkout import PurchaseExecution
            # Find products older than 30 days with no recent purchase execution
            result = await db.execute(
                select(Product)
                .where(
                    Product.deleted_at.is_(None),
                    Product.created_at < expiration_threshold,
                    ~Product.id.in_(
                        select(ScrapingJob.product_id)
                        .join(PurchaseExecution, PurchaseExecution.order_id == ScrapingJob.order_id)
                        .where(PurchaseExecution.created_at >= expiration_threshold)
                    )
                )
                .limit(settings.PRODUCT_STALENESS_BATCH_SIZE)
            )
            products = list(result.scalars())
            if not products:
                return

            now = datetime.now(timezone.utc)
            for product in products:
                product.deleted_at = now
                product.status = "archived"
            
            await db.commit()


async def _amain() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    worker = PriceStalenessWorker(redis)
    try:
        await worker.run()
    finally:
        await redis.close()


def main() -> None:
    asyncio.run(_amain())
