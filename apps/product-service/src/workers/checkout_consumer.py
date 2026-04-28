from __future__ import annotations

import asyncio
import json
import logging
import signal
import socket
from datetime import datetime, timezone
import time

from opentelemetry import trace
from sk_shared.constants import QueueName
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.core.distributed_lock import DistributedLock
from src.middleware.metrics import CHECKOUT_JOB_DURATION
from src.services.checkout import CheckoutAgentService

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("product-service.worker.checkout")


class CheckoutConsumer:
    def __init__(self, max_concurrency: int = 5) -> None:
        self.running = True
        self._sem = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency

    async def run(self) -> None:
        logger.info("Starting CheckoutConsumer hostname=%s max_concurrency=%s", socket.gethostname(), self.max_concurrency)
        redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
        
        loop = asyncio.get_running_loop()
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
                    import redis
                    if isinstance(e, (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError)):
                        await asyncio.sleep(5)
                        continue
                    logger.error(f"Error in CheckoutConsumer loop: {e}", exc_info=True)
                    await asyncio.sleep(1)
        finally:
            logger.info("Closing CheckoutConsumer...")
            await redis.close()

    async def _process_with_sem(self, payload: dict, redis) -> None:
        async with self._sem:
            start = time.perf_counter()
            status_label = "failed"
            with tracer.start_as_current_span(
                "checkout_consumer.process",
                attributes={
                    "execution_id": str(payload.get("execution_id", "")),
                    "correlation_id": str(payload.get("correlation_id", "")),
                },
            ):
                try:
                    execution_id = payload.get("execution_id")
                    if not execution_id:
                        status_label = "invalid_payload"
                        await self._send_to_dlq(payload, "Missing execution_id", redis)
                        return

                    if not await self._check_idempotency(redis, execution_id):
                        logger.info("Skipping duplicate checkout execution_id=%s", execution_id)
                        status_label = "duplicate"
                        return
                    async with SessionLocal() as db:
                        async with DistributedLock(redis, f"checkout:{execution_id}", timeout=300):
                            service = CheckoutAgentService(db, redis)
                            await service.process_job(payload)
                        status_label = "processed"
                except Exception as e:
                    logger.exception("Checkout worker task failed")
                    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
                    execution_id = payload.get("execution_id")
                    if isinstance(e, PlaywrightTimeoutError) and execution_id:
                        logger.info("Playwright timeout, requeuing job")
                        await redis.lpush(QueueName.CHECKOUT, json.dumps(payload))
                    else:
                        await self._send_to_dlq(payload, str(e), redis)
                        # Ensure execution is marked failed if it goes to DLQ
                        if execution_id:
                            try:
                                async with SessionLocal() as db:
                                    from sqlalchemy import text
                                    await db.execute(text("UPDATE purchase_executions SET status = 'failed' WHERE uuid = :uuid"), {"uuid": execution_id})
                                    await db.commit()
                            except Exception:
                                pass
                finally:
                    execution_id = payload.get("execution_id")
                    if execution_id:
                        await redis.delete(f"sk:checkout:processing:{execution_id}")
                    CHECKOUT_JOB_DURATION.labels(status=status_label).observe(time.perf_counter() - start)

    async def _check_idempotency(self, redis, execution_uuid: str) -> bool:
        key = f"sk:checkout:processing:{execution_uuid}"
        locked = await redis.redis.set(key, "1", ex=600, nx=True)
        return bool(locked)

    async def _send_to_dlq(self, payload: dict, error: str, redis) -> None:
        dlq_entry = {
            **payload,
            "dlq_error": error,
            "dlq_at": datetime.now(timezone.utc).isoformat(),
            "worker": socket.gethostname(),
        }
        # GAP-A FIX: Use short queue name to avoid doubled prefix.
        # Was: sk:queue:dlq:sk:queue:checkout — now: sk:queue:dlq:checkout
        await redis.lpush("sk:queue:dlq:checkout", json.dumps(dlq_entry))


async def _amain() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL)
    consumer = CheckoutConsumer()
    await consumer.run()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()