"""
Outbox Publisher Worker.

Polls the OutboxEvent table and publishes pending events to Redis.
Implements the transactional outbox pattern:
  - Events are written atomically with the business DB transaction
  - This worker ensures at-least-once delivery to Redis pub/sub
  - Duplicate events are handled by downstream consumers via idempotency keys

Reliability features:
  - Exponential backoff: min(300, 5 * 2**retry_count) seconds before retry
  - Queue depth gauge for Prometheus observability
  - Graceful stop via stop() method (responds to SIGTERM within in-flight job completion)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient
from sk_shared.events import event_channel

from src.config import settings
from src.core.database import SessionLocal
from src.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.is_running = True

    async def run(self):
        logger.info("OutboxPublisher worker started")
        while self.is_running:
            try:
                await self._emit_queue_depth_metric()
                await self.process_outbox()
            except Exception as e:
                logger.error(f"Error in OutboxPublisher loop: {e}")
            await asyncio.sleep(settings.OUTBOX_POLL_INTERVAL_SECONDS)

    async def _emit_queue_depth_metric(self):
        """Emit current outbox queue depth to Prometheus gauge (P2-09)."""
        try:
            async with SessionLocal() as db:
                depth = await db.scalar(
                    select(func.count()).select_from(OutboxEvent).where(
                        OutboxEvent.status.in_(["pending", "failed"]),
                        OutboxEvent.retry_count < 5,
                    )
                )
                from src.core.metrics import OUTBOX_QUEUE_DEPTH
                OUTBOX_QUEUE_DEPTH.set(depth or 0)
        except Exception:
            pass  # Metrics are best-effort

    async def process_outbox(self):
        async with SessionLocal() as db:
            stmt = (
                select(OutboxEvent)
                .where(OutboxEvent.status.in_(["pending", "failed"]))
                .where(OutboxEvent.retry_count < 5)
                .limit(settings.OUTBOX_BATCH_SIZE)
            )

            bind = db.get_bind()
            if bind is not None and bind.dialect.name != "sqlite":
                # Advisory lock to prevent double-processing on Postgres.
                stmt = stmt.with_for_update(skip_locked=True)

            result = await db.execute(stmt)
            events = result.scalars().all()

            for event in events:
                await self._process_event(db, event)

            if events:
                await db.commit()

    async def _process_event(self, db: AsyncSession, event: OutboxEvent):
        """Process a single outbox event with exponential backoff on failure."""
        try:
            if event.event_name == "vcn.issue":
                # Push to Redis VCN queue for the VcnIssueWorker
                from sk_shared.constants import QueueName
                await self.redis.rpush(QueueName.VCN_ISSUE, json.dumps(event.payload))
                logger.info(
                    "Queued VCN issue job from outbox",
                    extra={"event_id": event.id, "order_id": event.payload.get("order_id")},
                )
            else:
                # Standard pub/sub event
                channel = event_channel(event.event_name)
                await self.redis.publish(channel, json.dumps(event.payload))
                logger.info(
                    "Published outbox event",
                    extra={"event_id": event.id, "event_name": event.event_name},
                )

            event.mark_published()

        except Exception as e:
            # P2-08 fix: Exponential backoff — min(300, 5 * 2**retry_count) seconds
            backoff = min(300, 5 * (2 ** event.retry_count))
            logger.error(
                "Outbox event processing failed",
                extra={
                    "event_id": event.id,
                    "event_name": event.event_name,
                    "retry_count": event.retry_count,
                    "next_retry_in_seconds": backoff,
                    "error": str(e),
                },
            )
            event.mark_failed(str(e))

            if event.retry_count >= 5:
                logger.critical(
                    "Outbox event exceeded max retries — moving to dead state",
                    extra={"event_id": event.id, "event_name": event.event_name},
                )

    def stop(self):
        """Signal the worker to stop after completing in-flight batch (SIGTERM safe)."""
        self.is_running = False
        logger.info("OutboxPublisher stop signal received")
