"""
VCN Issue Worker.

Consumes VCN issuance jobs from the Redis queue:
  sk:queue:vcn_issue

Features:
  - Concurrency control via asyncio.Semaphore
  - Graceful shutdown (SIGTERM / SIGINT)
  - DLQ: after DLQ_MAX_RETRIES failures, job is pushed to sk:queue:dlq:vcn_issue
  - Structured JSON logging for each job
  - Retry counter tracked per-job in the payload
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from decimal import Decimal

from sk_shared.constants import QueueName
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.core.logging import setup_logging
from src.services.vcn import VcnService

logger = logging.getLogger(__name__)

DLQ_KEY = "sk:queue:dlq:vcn_issue"


class VcnIssueWorker:
    def __init__(self, concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running = True

    def stop(self) -> None:
        logger.info("VCN worker received shutdown signal")
        self._running = False

    async def run(self) -> None:
        redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
        logger.info("VCN issue worker started", extra={"concurrency": self._semaphore._value})

        try:
            while self._running:
                job = await redis.redis.brpop(QueueName.VCN_ISSUE, timeout=5)
                if job is None:
                    await asyncio.sleep(0)
                    continue

                raw_payload = job[1]
                asyncio.create_task(self._process(raw_payload, redis))
        finally:
            await redis.close()
            logger.info("VCN issue worker stopped cleanly")

    async def _process(self, raw_payload: bytes, redis) -> None:
        async with self._semaphore:
            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("Unparseable VCN job payload", extra={"error": str(exc)})
                return

            order_id = payload.get("order_id")
            retry_count = payload.get("_retry_count", 0)

            try:
                async with SessionLocal() as db:
                    service = VcnService(db, redis)
                    await service.issue_vcn(
                        order_id=order_id,
                        amount_pkr=Decimal(str(payload.get("amount_pkr", "0"))),
                        merchant_domain=payload.get("merchant_domain"),
                    )
                logger.info("VCN job completed", extra={"order_id": order_id})

            except Exception as exc:
                logger.error(
                    "VCN job failed",
                    extra={"order_id": order_id, "error": str(exc), "retry_count": retry_count},
                )
                if retry_count < settings.DLQ_MAX_RETRIES:
                    payload["_retry_count"] = retry_count + 1
                    # Exponential backoff: 2^retry * 5 seconds (5, 10, 20, 40...)
                    backoff_delay = 5 * (2 ** retry_count)
                    logger.info(
                        "VCN job waiting for backoff", 
                        extra={"order_id": order_id, "retry_count": retry_count + 1, "delay_sec": backoff_delay}
                    )
                    await asyncio.sleep(backoff_delay)
                    await redis.redis.lpush(QueueName.VCN_ISSUE, json.dumps(payload))
                    logger.info("VCN job re-queued after backoff", extra={"order_id": order_id})
                else:
                    await redis.redis.lpush(DLQ_KEY, raw_payload)
                    logger.error(
                        "VCN job sent to DLQ — max retries exceeded",
                        extra={"order_id": order_id, "dlq": DLQ_KEY},
                    )


def main() -> None:
    setup_logging("vcn-issue-worker", settings.LOG_LEVEL)
    worker = VcnIssueWorker(concurrency=settings.VCN_WORKER_CONCURRENCY)

    loop = asyncio.get_event_loop()

    def _handle_signal(*_):
        worker.stop()

    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    loop.run_until_complete(worker.run())


if __name__ == "__main__":
    main()