from __future__ import annotations

import asyncio
import logging
import signal
import socket

from sk_shared.database import SessionLocal
from sk_shared.redis_client import RedisClient, get_redis_client

from src.config import settings
from src.services.execution_reaper_service import ExecutionReaperService

logger = logging.getLogger(__name__)
LOCK_KEY = "sk:lock:execution_reaper_worker"
LOCK_TTL_SECONDS = 7200


class ExecutionReaperWorker:
    """Scheduled sweep that reaps `PurchaseExecution` rows stuck at
    status='running' -- see ExecutionReaperService for why this exists
    (HIGH-02: crashed checkout workers otherwise leave rows stuck forever,
    with the admin retry endpoint explicitly no-op'ing on 'running').

    Follows the same run-loop shape as this codebase's other single-tenant
    scheduled workers (PriceStalenessWorker, ProhibitedCatalogWorker):
    Redis NX lock so only one replica does the sweep, then sleep for the
    configured interval.
    """

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

        logger.info("ExecutionReaperWorker started")

        while self.running:
            acquired = await self.redis.redis.set(LOCK_KEY, socket.gethostname(), ex=LOCK_TTL_SECONDS, nx=True)
            if acquired:
                try:
                    await self._reap_once()
                finally:
                    await self.redis.redis.delete(LOCK_KEY)

            for _ in range(settings.EXECUTION_REAPER_INTERVAL_SECONDS):
                if not self.running:
                    break
                await asyncio.sleep(1)

    async def _reap_once(self) -> None:
        async with SessionLocal() as db:
            reaped = await ExecutionReaperService(db).reap_all_stuck()
            if reaped:
                logger.warning(
                    "ExecutionReaperWorker reaped %d stuck execution(s): %s",
                    len(reaped),
                    [str(e.uuid) for e in reaped],
                )


async def _amain() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    worker = ExecutionReaperWorker(redis)
    try:
        await worker.run()
    finally:
        await redis.close()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
