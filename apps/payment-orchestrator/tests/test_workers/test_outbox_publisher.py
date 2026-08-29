"""
Tests for OutboxPublisher worker.

Covers:
  - Publisher processes pending events and marks them published
  - Publisher publishes vcn.issue events to Redis VCN queue
  - Publisher hands standard events off durably via a Redis Stream (XADD)
  - Publisher increments retry_count on failure
  - Publisher stops processing events past retry_count=5
  - stop() method signals graceful shutdown
  - PO-CRIT-03: stream delivery loop (XREADGROUP/XACK) actually forwards to
    the legacy pub/sub channel, and a crash between XREADGROUP and XACK
    leaves the entry claimable (XAUTOCLAIM) instead of losing it
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.models.outbox import OutboxEvent
from src.workers.outbox_publisher import (
    OUTBOX_CONSUMER_GROUP,
    OUTBOX_STREAM_KEY,
    OutboxPublisher,
)

pytestmark = pytest.mark.asyncio


async def _create_outbox_event(db_session, event_name: str, payload: dict) -> OutboxEvent:
    event = OutboxEvent(event_name=event_name, payload=payload, status="pending")
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


async def test_publisher_marks_event_published_after_success(db_session, redis_mock):
    """OutboxPublisher must mark events as 'published' after successful delivery."""
    event = await _create_outbox_event(
        db_session,
        "payment.confirmed",
        {"payload": {"workflow_id": 1, "order_id": 42}},
    )

    publisher = OutboxPublisher(redis_mock)
    # Process directly
    await publisher._process_event(db_session, event)
    await db_session.commit()

    assert event.status == "published"
    assert event.published_at is not None


async def test_publisher_queues_vcn_issue_to_redis_list(db_session, redis_mock):
    """vcn.issue outbox events must be pushed to the VCN_ISSUE Redis list, not pub/sub."""
    from sk_shared.constants import QueueName

    event = await _create_outbox_event(
        db_session,
        "vcn.issue",
        {"order_id": 10, "amount_pkr": "5200", "merchant_domain": None},
    )

    publisher = OutboxPublisher(redis_mock)
    await publisher._process_event(db_session, event)

    # Verify the event was pushed to the VCN queue (not pub/sub)
    queue_len = await redis_mock.redis.llen(QueueName.VCN_ISSUE)
    assert queue_len == 1

    raw = await redis_mock.redis.rpop(QueueName.VCN_ISSUE)
    payload = json.loads(raw)
    assert payload["order_id"] == 10


async def test_publisher_increments_retry_count_on_failure(db_session, redis_mock):
    """If publishing fails, retry_count must increment and status set to 'failed'."""
    event = await _create_outbox_event(
        db_session,
        "payment.confirmed",
        {"payload": {"workflow_id": 2}},
    )

    publisher = OutboxPublisher(redis_mock)

    # Standard events are now handed off durably via XADD (see PO-CRIT-03) —
    # make that call raise to exercise the same retry/backoff path.
    with patch.object(redis_mock, "xadd", side_effect=Exception("Redis down")):
        await publisher._process_event(db_session, event)

    assert event.status == "failed"
    assert event.retry_count == 1
    assert event.last_error == "Redis down"


async def test_publisher_skips_events_at_max_retries(db_session, redis_mock):
    """Events with retry_count >= 5 must not be selected for processing."""
    # Create an event already at max retries
    event = OutboxEvent(
        event_name="payment.confirmed",
        payload={"payload": {"workflow_id": 3}},
        status="failed",
        retry_count=5,
    )
    db_session.add(event)
    await db_session.commit()

    # process_outbox queries for retry_count < 5 — this event should not be selected
    publisher = OutboxPublisher(redis_mock)
    # We patch SessionLocal to use our test session
    with patch("src.workers.outbox_publisher.SessionLocal") as mock_session_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_ctx

        await publisher.process_outbox()

    # The max-retry event should still be failed (not published)
    await db_session.refresh(event)
    assert event.status == "failed"
    assert event.retry_count == 5


async def test_publisher_calls_gateway_on_payment_confirmed_event(db_session, redis_mock):
    """P0-01: gateway.payment_confirmed events must POST to Gateway's internal
    confirm endpoint with the internal token, and mark the outbox event published
    on a 2xx response.
    """
    from src.config import settings

    event = await _create_outbox_event(
        db_session,
        "gateway.payment_confirmed",
        {"payment_id": 77, "gateway_txn_id": "GW-TXN-1", "status": "confirmed"},
    )

    publisher = OutboxPublisher(redis_mock)

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await publisher._process_event(db_session, event)
    await db_session.commit()

    assert event.status == "published"
    mock_client.post.assert_awaited_once()
    call_args = mock_client.post.await_args
    assert call_args.args[0] == f"{settings.GATEWAY_URL}/api/v1/internal/payments/77/confirm"
    assert call_args.kwargs["headers"]["X-Internal-Token"] == settings.INTERNAL_API_TOKEN
    assert call_args.kwargs["json"] == {"gateway_txn_id": "GW-TXN-1", "status": "confirmed"}


async def test_publisher_retries_gateway_payment_confirmed_on_http_failure(db_session, redis_mock):
    """A failed Gateway notification (e.g. Gateway temporarily down) must be
    retried like any other outbox event, not silently dropped.
    """
    event = await _create_outbox_event(
        db_session,
        "gateway.payment_confirmed",
        {"payment_id": 78, "gateway_txn_id": "GW-TXN-2", "status": "confirmed"},
    )

    publisher = OutboxPublisher(redis_mock)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await publisher._process_event(db_session, event)

    assert event.status == "failed"
    assert event.retry_count == 1
    assert "connection refused" in event.last_error


async def test_deliver_stream_events_publishes_to_channel_and_acks(db_session, redis_mock):
    """PO-CRIT-03: a standard event durably queued via _process_event (XADD)
    must be forwarded to its legacy pub/sub channel and XACK'd by
    deliver_stream_events(), leaving nothing pending in the consumer group."""
    from sk_shared.events import event_channel

    event = await _create_outbox_event(
        db_session,
        "payment.confirmed",
        {"payload": {"workflow_id": 99}},
    )

    publisher = OutboxPublisher(redis_mock)
    await publisher._process_event(db_session, event)
    await db_session.commit()
    assert event.status == "published"

    received = []

    async def _fake_publish(channel, message):
        received.append((channel, message))

    with patch.object(redis_mock, "publish", side_effect=_fake_publish):
        await publisher.deliver_stream_events()

    assert len(received) == 1
    channel, message = received[0]
    assert channel == event_channel("payment.confirmed")
    assert json.loads(message) == {"payload": {"workflow_id": 99}}

    # Fully acknowledged -- nothing left pending in the consumer group.
    pending = await redis_mock.redis.xpending(OUTBOX_STREAM_KEY, OUTBOX_CONSUMER_GROUP)
    assert pending["pending"] == 0


async def test_crashed_consumer_entry_is_reclaimed_not_lost(db_session, redis_mock):
    """PO-CRIT-03 durability regression test.

    Simulates a consumer/worker that read a stream entry (XREADGROUP) and
    then crashed before XACK'ing it -- exactly what a process kill between
    XREADGROUP and XACK looks like from Redis's point of view: the entry
    stays in the consumer group's Pending Entries List, attributed to a
    consumer that will never come back.

    Asserts the event is NOT lost: a second worker instance (e.g. this
    worker after a restart, or another replica) reclaims it via XAUTOCLAIM
    and completes delivery.
    """
    event = await _create_outbox_event(
        db_session,
        "payment.confirmed",
        {"payload": {"workflow_id": 100}},
    )

    crashed_publisher = OutboxPublisher(redis_mock, consumer_name="crashed-consumer")
    await crashed_publisher._process_event(db_session, event)
    await db_session.commit()

    # Simulate the crash: read the entry into the PEL (as XREADGROUP does)
    # but never XACK it.
    await crashed_publisher._ensure_stream_group()
    read = await redis_mock.xreadgroup(
        OUTBOX_CONSUMER_GROUP, "crashed-consumer", streams={OUTBOX_STREAM_KEY: ">"}, count=10
    )
    assert read, "expected the XADD'd entry to be readable by XREADGROUP"

    # Confirm it is sitting unacknowledged in the PEL -- not delivered, not lost.
    pending_before = await redis_mock.redis.xpending(OUTBOX_STREAM_KEY, OUTBOX_CONSUMER_GROUP)
    assert pending_before["pending"] == 1

    # A second worker instance comes along. Bypass the real idle-time window
    # (STREAM_CLAIM_MIN_IDLE_MS) so the test doesn't have to sleep 30s --
    # what's under test is that XAUTOCLAIM reclaims it at all, not the timing.
    recovering_publisher = OutboxPublisher(redis_mock, consumer_name="recovering-consumer")
    received = []

    async def _fake_publish(channel, message):
        received.append((channel, message))

    with patch("src.workers.outbox_publisher.STREAM_CLAIM_MIN_IDLE_MS", 0), \
         patch.object(redis_mock, "publish", side_effect=_fake_publish):
        await recovering_publisher.deliver_stream_events()

    # The event was reclaimed and delivered by the second consumer, not dropped.
    assert len(received) == 1
    assert json.loads(received[0][1]) == {"payload": {"workflow_id": 100}}

    pending_after = await redis_mock.redis.xpending(OUTBOX_STREAM_KEY, OUTBOX_CONSUMER_GROUP)
    assert pending_after["pending"] == 0


async def test_publisher_stop_signals_graceful_shutdown():
    """stop() must set is_running to False."""
    from fakeredis.aioredis import FakeRedis
    from sk_shared.redis_client import RedisClient

    redis = RedisClient(FakeRedis())
    publisher = OutboxPublisher(redis)

    assert publisher.is_running is True
    publisher.stop()
    assert publisher.is_running is False
