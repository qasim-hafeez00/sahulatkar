import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient
from sk_shared.events import event_channel

from src.core.database import SessionLocal
from src.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, redis: RedisClient):
        self.redis = redis
        self.is_running = True

    async def run(self):
        logger.info("Starting OutboxPublisher worker")
        while self.is_running:
            try:
                await self.process_outbox()
            except Exception as e:
                logger.error(f"Error in OutboxPublisher: {e}")
            await asyncio.sleep(5)  # Poll every 5 seconds

    async def process_outbox(self):
        async with SessionLocal() as db:
            result = await db.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status.in_(["pending", "failed"]))
                .where(OutboxEvent.retry_count < 5)
                .limit(50)
            )
            events = result.scalars().all()

            for event in events:
                try:
                    if event.event_name == "vcn.issue":
                        # Push to Redis queue for the VCN worker
                        from sk_shared.constants import QueueName
                        await self.redis.rpush(QueueName.VCN_ISSUE, json.dumps(event.payload))
                        logger.info(f"Queued VCN issue job from outbox", extra={"event_id": event.id})
                    else:
                        # Standard pub/sub event
                        channel = event_channel(event.event_name)
                        await self.redis.publish(channel, json.dumps(event.payload))
                        logger.info(f"Published event {event.event_name} from outbox", extra={"event_id": event.id})
                    
                    event.mark_published()
                except Exception as e:
                    logger.error(f"Failed to process outbox event {event.id}: {e}")
                    event.mark_failed(str(e))
            
            if events:
                await db.commit()

    def stop(self):
        self.is_running = False
