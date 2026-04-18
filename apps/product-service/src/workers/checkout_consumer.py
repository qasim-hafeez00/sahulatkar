from __future__ import annotations

import asyncio
import json
import logging
import signal
import socket
from datetime import datetime, timezone

from sk_shared.constants import QueueName
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.services.checkout_agent import CheckoutAgentService

logger = logging.getLogger(__name__)


class CheckoutConsumer:
    def __init__(self, max_concurrency: int = 5) -> None:
        self.running = True
        self._sem = asyncio.Semaphore(max_concurrency)

    async def run(self) -> None:
        logger.info("Starting CheckoutConsumer...")
        redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
        
        loop = asyncio.get_event_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: setattr(self, "running", False))
        except NotImplementedError:
            pass

        try:
            while self.running:
                try:
                    # GAP-01: FIFO - brpop pops from RIGHT
                    job = await redis.redis.brpop(QueueName.CHECKOUT, timeout=5)
                    if job is None:
                        continue

                    logger.info(f"Processing checkout job: {job[1].decode('utf-8')}")
                    
                    try:
                        payload = json.loads(job[1].decode("utf-8"))
                        asyncio.create_task(self._process_with_sem(payload, redis))
                    except Exception as e:
                        await self._send_to_dlq({"raw_data": job[1].decode("utf-8")}, str(e), redis)
                        
                except Exception as e:
                    logger.error(f"Error in CheckoutConsumer loop: {e}", exc_info=True)
                    await asyncio.sleep(1)
        finally:
            logger.info("Closing CheckoutConsumer...")
            await redis.close()

    async def _process_with_sem(self, payload: dict, redis) -> None:
        async with self._sem:
            try:
                async with SessionLocal() as db:
                    service = CheckoutAgentService(db, redis)
                    await service.process_job(payload)
            except Exception as e:
                logger.exception("Checkout worker task failed")
                await self._send_to_dlq(payload, str(e), redis)

    async def _send_to_dlq(self, payload: dict, error: str, redis) -> None:
        dlq_entry = {
            **payload,
            "dlq_error": error,
            "dlq_at": datetime.now(timezone.utc).isoformat(),
            "worker": socket.gethostname()
        }
        await redis.lpush(f"sk:queue:dlq:{QueueName.CHECKOUT}", json.dumps(dlq_entry))


async def main() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    consumer = CheckoutConsumer()
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())