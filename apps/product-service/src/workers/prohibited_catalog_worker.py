import asyncio
import logging
import signal
import socket
from datetime import datetime, timezone

from sqlalchemy import select

from sk_shared.database import SessionLocal
from sk_shared.models.product import Product, ProhibitedCategory
from sk_shared.redis_client import RedisClient, get_redis_client
from src.config import settings

logger = logging.getLogger(__name__)
LOCK_KEY = "sk:lock:prohibited_catalog_worker"
LOCK_TTL_SECONDS = 7200

class ProhibitedCatalogWorker:
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

        logger.info("ProhibitedCatalogWorker started")

        while self.running:
            acquired = await self.redis.redis.set(LOCK_KEY, socket.gethostname(), ex=LOCK_TTL_SECONDS, nx=True)
            if acquired:
                try:
                    await self._scan_products()
                finally:
                    await self.redis.redis.delete(LOCK_KEY)
            
            # Run once a day
            for _ in range(86400):
                if not self.running:
                    break
                await asyncio.sleep(1)

    async def _scan_products(self) -> None:
        async with SessionLocal() as db:
            categories = list(await db.scalars(select(ProhibitedCategory)))
            if not categories:
                return

            # Fetch active products
            result = await db.execute(
                select(Product)
                .where(
                    Product.deleted_at.is_(None),
                    Product.is_prohibited.is_(False)
                )
            )
            products = list(result.scalars())
            
            banned_count = 0
            now = datetime.now(timezone.utc)
            for product in products:
                is_banned = False
                ban_reason = ""
                # Check domain
                domain = (product.canonical_url or "").lower()
                
                # Check keywords
                for category in categories:
                    for keyword in category.keywords:
                        if keyword.lower() in domain or (product.name and keyword.lower() in product.name.lower()):
                            is_banned = True
                            ban_reason = f"Category {category.category_name} keyword '{keyword}'"
                            break
                    if is_banned:
                        break
                
                if is_banned:
                    product.is_prohibited = True
                    product.shariah_category = ban_reason
                    product.status = "prohibited"
                    product.updated_at = now
                    banned_count += 1
                    
            if banned_count > 0:
                logger.info("ProhibitedCatalogWorker banned %d products", banned_count)
                await db.commit()

async def _amain() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    worker = ProhibitedCatalogWorker(redis)
    try:
        await worker.run()
    finally:
        await redis.close()

def main() -> None:
    asyncio.run(_amain())

if __name__ == "__main__":
    main()
