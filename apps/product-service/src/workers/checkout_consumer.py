from __future__ import annotations

import asyncio
import json
import logging

from sk_shared.constants import QueueName
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.services.checkout_agent import CheckoutAgentService

logger = logging.getLogger(__name__)


class CheckoutConsumer:
    def __init__(self) -> None:
        self.running = True

    async def run(self) -> None:
        logger.info("Starting CheckoutConsumer...")
        redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
        try:
            while self.running:
                try:
                    job = await redis.redis.brpop(QueueName.CHECKOUT, timeout=5)
                    if job is None:
                        await asyncio.sleep(0.1)
                        continue

                    logger.info(f"Processing checkout job: {job[1].decode('utf-8')}")
                    payload = json.loads(job[1].decode("utf-8"))
                    
                    async with SessionLocal() as db:
                        service = CheckoutAgentService(db, redis)
                        await service.process_job(payload)
                        
                except Exception as e:
                    logger.error(f"Error in CheckoutConsumer loop: {e}", exc_info=True)
                    await asyncio.sleep(1)
        finally:
            logger.info("Closing CheckoutConsumer...")
            await redis.close()


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    consumer = CheckoutConsumer()
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())