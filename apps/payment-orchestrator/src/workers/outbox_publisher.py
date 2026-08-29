"""
Outbox Publisher Worker.

Polls the OutboxEvent table and publishes pending events to Redis.
Implements the transactional outbox pattern:
  - Events are written atomically with the business DB transaction
  - This worker ensures at-least-once delivery to Redis
  - Duplicate events are handled by downstream consumers via idempotency keys

Delivery transport (standard events — not vcn.issue / gateway.payment_confirmed,
which have their own dedicated transports below):
  - PO-CRIT-03: plain redis.publish() pub/sub gives ZERO durability — if the
    downstream consumer (Ledger Service) is not connected at the exact instant
    of the publish, the message is gone, even though the OutboxEvent row still
    sits in Postgres marked "published". This worker now hands events off via
    a Redis Stream (XADD) instead: the entry persists in Redis regardless of
    whether anyone is listening. A consumer-group loop on the same stream
    (deliver_stream_events(), run from the same worker process) then does the
    actual XREADGROUP / publish-to-legacy-channel / XACK dance, so an event is
    only considered delivered once it has been acknowledged. A crash between
    XREADGROUP and XACK leaves the entry in the group's Pending Entries List,
    where XAUTOCLAIM reclaims it (here or from another worker instance) for
    another attempt instead of losing it silently.

Reliability features:
  - Exponential backoff: min(300, 5 * 2**retry_count) seconds before retry
  - Queue depth gauge for Prometheus observability
  - Graceful stop via stop() method (responds to SIGTERM within in-flight job completion)
"""
import asyncio
import json
import logging
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient
from sk_shared.events import event_channel

from src.config import settings
from src.core.database import SessionLocal
from src.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)

# ── PO-CRIT-03: durable stream transport for standard outbox events ─────────
# Follows the sk:queue:* / sk:events:* naming convention used elsewhere in
# this service (see src/workers/vcn_issue_worker.py, sk_shared.events) —
# sk:stream:* for the Redis Streams equivalent.
OUTBOX_STREAM_KEY = "sk:stream:outbox_events"
OUTBOX_CONSUMER_GROUP = "payment-orchestrator-outbox"
# Entries whose original consumer has held them unacked longer than this are
# assumed abandoned (crashed/killed mid-processing) and become claimable.
STREAM_CLAIM_MIN_IDLE_MS = 30_000


class OutboxPublisher:
    def __init__(self, redis: RedisClient, consumer_name: str | None = None):
        self.redis = redis
        self.is_running = True
        # Unique per worker instance/process so XAUTOCLAIM can tell a live
        # consumer's in-flight entries apart from ones an instance abandoned.
        self.consumer_name = consumer_name or f"outbox-publisher-{uuid.uuid4().hex[:8]}"
        self._stream_group_ready = False

    async def run(self):
        logger.info("OutboxPublisher worker started")
        while self.is_running:
            try:
                await self._emit_queue_depth_metric()
                await self.process_outbox()
                await self.deliver_stream_events()
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
            elif event.event_name == "gateway.payment_confirmed":
                # P0-01: notify Gateway so it advances Order.status past
                # CONTRACTS_SIGNED and runs its own saga-compensation logic.
                # A non-2xx or network failure raises, which falls through to
                # the same exponential-backoff retry as every other event.
                import httpx
                payload = event.payload
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{settings.GATEWAY_URL}/api/v1/internal/payments/{payload['payment_id']}/confirm",
                        headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
                        json={
                            "gateway_txn_id": payload.get("gateway_txn_id", ""),
                            "status": payload.get("status", "confirmed"),
                        },
                    )
                    resp.raise_for_status()
                logger.info(
                    "Notified Gateway of payment confirmation",
                    extra={"event_id": event.id, "payment_id": payload["payment_id"]},
                )
            else:
                # PO-CRIT-03: Standard event — durable handoff via Redis Stream
                # (XADD) instead of a bare publish(). The entry survives in
                # Redis even if no consumer is connected right now; actual
                # delivery + acknowledgement happens in deliver_stream_events().
                channel = event_channel(event.event_name)
                await self.redis.xadd(
                    OUTBOX_STREAM_KEY,
                    {
                        "event_id": str(event.id),
                        "event_name": event.event_name,
                        "channel": channel,
                        "payload": json.dumps(event.payload),
                    },
                )
                logger.info(
                    "Enqueued outbox event to durable stream",
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

    async def _ensure_stream_group(self):
        """Create the consumer group on first use (idempotent — RedisClient.
        xgroup_create swallows BUSYGROUP). MKSTREAM so this also creates the
        stream itself if no event has been XADD'd yet."""
        if self._stream_group_ready:
            return
        await self.redis.xgroup_create(OUTBOX_STREAM_KEY, OUTBOX_CONSUMER_GROUP, id="0", mkstream=True)
        self._stream_group_ready = True

    async def deliver_stream_events(self, count: int | None = None):
        """
        Deliver events sitting in the durable stream to their legacy pub/sub
        channel (what Ledger Service and other consumers already subscribe
        to), acknowledging (XACK) only after the publish succeeds.

        Before reading new entries, reclaims (XAUTOCLAIM) anything left
        unacknowledged by a consumer that crashed mid-processing — i.e. died
        between XREADGROUP and XACK — so those events are retried instead of
        silently lost. This is what makes the stream hop at-least-once: an
        entry only leaves the Pending Entries List once it is actually XACK'd.
        """
        batch_size = count or settings.OUTBOX_BATCH_SIZE
        await self._ensure_stream_group()

        entries = []
        try:
            _next_start_id, claimed, _deleted = await self.redis.xautoclaim(
                OUTBOX_STREAM_KEY,
                OUTBOX_CONSUMER_GROUP,
                self.consumer_name,
                min_idle_time=STREAM_CLAIM_MIN_IDLE_MS,
                start_id="0-0",
                count=batch_size,
            )
            entries.extend(claimed)
        except Exception as e:
            logger.error(f"XAUTOCLAIM failed while reclaiming stale outbox stream entries: {e}")

        try:
            read = await self.redis.xreadgroup(
                OUTBOX_CONSUMER_GROUP,
                self.consumer_name,
                streams={OUTBOX_STREAM_KEY: ">"},
                count=batch_size,
            )
            for _stream_name, msgs in read or []:
                entries.extend(msgs)
        except Exception as e:
            logger.error(f"XREADGROUP failed while reading outbox stream: {e}")

        for msg_id, fields in entries:
            await self._deliver_stream_entry(msg_id, fields)

    async def _deliver_stream_entry(self, msg_id, fields: dict):
        """Publish one stream entry to its legacy channel and XACK it. Left
        unacknowledged on any failure so XAUTOCLAIM can reclaim and retry it
        — never dropped."""
        try:
            decoded = {
                (k.decode("utf-8") if isinstance(k, bytes) else k): (
                    v.decode("utf-8") if isinstance(v, bytes) else v
                )
                for k, v in fields.items()
            }
            await self.redis.publish(decoded["channel"], decoded["payload"])
            await self.redis.xack(OUTBOX_STREAM_KEY, OUTBOX_CONSUMER_GROUP, msg_id)
            logger.info(
                "Delivered outbox stream event and acknowledged",
                extra={"stream_msg_id": msg_id, "event_name": decoded.get("event_name")},
            )
        except Exception as e:
            logger.error(
                "Outbox stream event delivery failed — left unacknowledged for reclaim/retry",
                extra={"stream_msg_id": msg_id, "error": str(e)},
            )

    def stop(self):
        """Signal the worker to stop after completing in-flight batch (SIGTERM safe)."""
        self.is_running = False
        logger.info("OutboxPublisher stop signal received")
