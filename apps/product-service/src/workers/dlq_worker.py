from __future__ import annotations

import asyncio
import logging

from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.middleware.metrics import DLQ_DEPTH
from src.services.dlq_service import DLQService

logger = logging.getLogger(__name__)


class DLQMonitorWorker:
    def __init__(self, redis, interval_seconds: int = 60) -> None:
        self.redis = redis
        self.interval_seconds = interval_seconds
        self.running = True
        self.service = DLQService(redis)

    async def run(self) -> None:
        while self.running:
            await self._check_and_alert()
            await asyncio.sleep(self.interval_seconds)

    async def _check_and_alert(self) -> dict[str, int]:
        stats = await self.service.get_stats()
        for queue_name, depth in stats.items():
            DLQ_DEPTH.labels(queue=queue_name).set(depth)
            if queue_name == "checkout" and depth > 50:
                logger.warning("checkout_dlq_overflow depth=%s", depth)
            if queue_name == "scraping" and depth > 100:
                logger.warning("scraping_dlq_overflow depth=%s", depth)
        return stats


async def _amain() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    worker = DLQMonitorWorker(redis)
    try:
        await worker.run()
    finally:
        await redis.close()


def main() -> None:
    asyncio.run(_amain())