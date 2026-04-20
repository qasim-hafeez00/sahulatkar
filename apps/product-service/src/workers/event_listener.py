"""
Redis pub/sub listener for cross-service events.

Subscriptions:
  sk:events:vcn.issued  → trigger checkout agent job
"""
import asyncio
import json
import logging
import signal
import traceback

from opentelemetry import trace
from sqlalchemy import select

from sk_shared.database import SessionLocal
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.services.checkout import CheckoutAgentService

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("product-service.worker.event-listener")

CHANNEL_VCN_ISSUED = "sk:events:vcn.issued"
CHANNEL_ORDER_CANCELLED = "sk:events:order.cancelled"

class EventListenerWorker:
    def __init__(self) -> None:
        self.running = True

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: setattr(self, "running", False))
        except NotImplementedError:
            pass

        while self.running:
            redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
            pubsub = redis.redis.pubsub()
            await pubsub.subscribe(CHANNEL_VCN_ISSUED, CHANNEL_ORDER_CANCELLED)
            logger.info("EventListenerWorker subscribed to %s and %s", CHANNEL_VCN_ISSUED, CHANNEL_ORDER_CANCELLED)

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
                        correlation_id = envelope.get("correlation_id")
                        logger.info("event_received event=%s correlation_id=%s", event_name, correlation_id)

                        with tracer.start_as_current_span(
                            "event_listener.handle",
                            attributes={
                                "event_name": str(event_name or ""),
                                "correlation_id": str(correlation_id or ""),
                            },
                        ):
                            if event_name == "vcn.issued":
                                await self._handle_vcn_issued(payload, redis)
                            elif event_name == "order.cancelled":
                                await self._handle_order_cancelled(payload, redis)
                    except Exception as exc:
                        logger.error("EventListenerWorker: error processing message: %s", exc)
                        logger.error(traceback.format_exc())
            except Exception as exc:
                logger.error("Event listener disconnected: %s", exc)
            finally:
                await pubsub.unsubscribe(CHANNEL_VCN_ISSUED, CHANNEL_ORDER_CANCELLED)
                await redis.close()

            if self.running:
                await asyncio.sleep(5)

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

    async def _handle_order_cancelled(self, payload: dict, redis) -> None:
        order_id = payload.get("order_id")
        if not order_id:
            return
        async with SessionLocal() as db:
            execution = await db.scalar(
                select(PurchaseExecution)
                .where(
                    PurchaseExecution.order_id == order_id,
                    PurchaseExecution.status.in_(["queued", "running", "pending_verification"]),
                )
                .order_by(PurchaseExecution.created_at.desc())
            )
            if execution is None:
                return
            execution.status = "cancelled"
            execution.completed_at = execution.completed_at or execution.created_at
            await db.commit()

            # Remove any queued payloads for this execution/order from Redis checkout queue.
            try:
                items = await redis.redis.lrange("sk:queue:checkout", 0, -1)
                for item in items:
                    payload_raw = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                    try:
                        obj = json.loads(payload_raw)
                    except Exception:
                        continue
                    queued_order_id = obj.get("order_id")
                    same_order = str(queued_order_id) == str(order_id)
                    same_execution = str(obj.get("execution_id")) == str(execution.uuid)
                    if same_execution or same_order:
                        await redis.redis.lrem("sk:queue:checkout", 1, item)
            except Exception as exc:
                logger.warning("Failed to clean cancelled order from checkout queue order_id=%s: %s", order_id, exc)

# ---------------------------------------------------------------------------
# BUG-04 FIX: Callable main() required by pyproject.toml entry point:
#   event-listener = "src.workers.event_listener:main"
# The old "if __name__ == '__main__'" block is NOT callable as an entry point.
# ---------------------------------------------------------------------------
def main() -> None:  # noqa: D401
    """Entry point declared in pyproject.toml as ``event-listener``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    worker = EventListenerWorker()
    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
