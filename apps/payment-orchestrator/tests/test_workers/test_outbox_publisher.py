"""
Tests for OutboxPublisher worker.

Covers:
  - Publisher processes pending events and marks them published
  - Publisher publishes vcn.issue events to Redis VCN queue
  - Publisher publishes standard events via pub/sub channel
  - Publisher increments retry_count on failure
  - Publisher stops processing events past retry_count=5
  - stop() method signals graceful shutdown
"""
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from src.models.outbox import OutboxEvent
from src.workers.outbox_publisher import OutboxPublisher

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

    # Make publish raise an exception
    with patch.object(redis_mock, "publish", side_effect=Exception("Redis down")):
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


async def test_publisher_stop_signals_graceful_shutdown():
    """stop() must set is_running to False."""
    from fakeredis.aioredis import FakeRedis
    from sk_shared.redis_client import RedisClient

    redis = RedisClient(FakeRedis())
    publisher = OutboxPublisher(redis)

    assert publisher.is_running is True
    publisher.stop()
    assert publisher.is_running is False
