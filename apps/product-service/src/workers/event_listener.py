"""
Redis pub/sub listener for cross-service events.

Subscriptions:
  sk:events:vcn.issued  → trigger checkout agent job
"""
import asyncio
import json
import logging
import traceback

from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.services.checkout_agent import CheckoutAgentService

logger = logging.getLogger(__name__)

CHANNEL_VCN_ISSUED = "sk:events:vcn.issued"

class EventListenerWorker:
    def __init__(self) -> None:
        self.running = True

    async def run(self) -> None:
        # Use a fresh redis client for pubsub
        redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
        pubsub = redis.redis.pubsub()
        await pubsub.subscribe(CHANNEL_VCN_ISSUED)
        logger.info("EventListenerWorker subscribed to %s", CHANNEL_VCN_ISSUED)

        try:
            async for message in pubsub.listen():
                if not self.running:
                    break
                if message["type"] != "message":
                    continue
                try:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    
                    envelope = json.loads(data)
                    payload = envelope["payload"]
                    event_name = envelope.get("event")
                    
                    if event_name == "vcn.issued":
                        await self._handle_vcn_issued(payload, redis)
                except Exception as exc:
                    logger.error("EventListenerWorker: error processing message: %s", exc)
                    logger.error(traceback.format_exc())
        finally:
            await pubsub.unsubscribe(CHANNEL_VCN_ISSUED)
            await redis.close()

    async def _handle_vcn_issued(self, payload: dict, redis) -> None:
        async with SessionLocal() as db:
            service = CheckoutAgentService(db, redis)
            await service.queue_job(
                order_id=payload["order_id"],
                vcn_id=payload["vcn_id"],
                correlation_id=payload.get("correlation_id"),
            )
            logger.info("Queued checkout job for order_id=%s vcn_id=%s",
                        payload["order_id"], payload["vcn_id"])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    worker = EventListenerWorker()
    asyncio.run(worker.run())
