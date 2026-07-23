"""Tests for src/workers/retry_worker.py."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from sk_shared.models.auth import User
from sk_shared.models.notification import Notification, NotificationDispatch
from sk_shared.redis_client import RedisClient

from src.workers import retry_worker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _patch_worker_infra(monkeypatch, db_session, redis_mock: RedisClient):
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(retry_worker, "SessionLocal", _session_cm)
    monkeypatch.setattr(retry_worker, "get_redis_client", lambda *a, **k: redis_mock)


async def _seed_notification_with_dispatch(db_session, *, status: str, next_retry_at) -> tuple[int, int]:
    user = User(phone="+923003000001", status="active")
    db_session.add(user)
    await db_session.flush()

    notification = Notification(
        user_id=user.id,
        source_event="billing.installment_due_d1",
        category="billing",
        priority="high",
        title="Reminder",
        body="Your installment is due",
        status="dispatching",
        idempotency_key=f"retry-test-{user.id}",
        channels_requested=["sms"],
        template_vars={},
    )
    db_session.add(notification)
    await db_session.flush()

    dispatch = NotificationDispatch(
        notification_id=notification.id,
        channel="sms",
        status=status,
        next_retry_at=next_retry_at,
    )
    db_session.add(dispatch)
    await db_session.commit()
    return notification.id, dispatch.id


async def test_requeues_due_retries(db_session, redis_mock: RedisClient):
    notification_id, _ = await _seed_notification_with_dispatch(
        db_session, status="retrying", next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    await retry_worker.process_retry_queue()

    from src.config import settings
    queued = await redis_mock.redis.lrange(settings.NOTIFICATION_QUEUE_KEY, 0, -1)
    assert [int(v) for v in queued] == [notification_id]


async def test_ignores_retries_not_yet_due(db_session, redis_mock: RedisClient):
    await _seed_notification_with_dispatch(
        db_session, status="retrying", next_retry_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )

    await retry_worker.process_retry_queue()

    from src.config import settings
    queued = await redis_mock.redis.lrange(settings.NOTIFICATION_QUEUE_KEY, 0, -1)
    assert queued == []


async def test_ignores_non_retrying_dispatches(db_session, redis_mock: RedisClient):
    await _seed_notification_with_dispatch(
        db_session, status="failed", next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    await retry_worker.process_retry_queue()

    from src.config import settings
    queued = await redis_mock.redis.lrange(settings.NOTIFICATION_QUEUE_KEY, 0, -1)
    assert queued == []


async def test_deduplicates_notification_ids_across_multiple_due_dispatches(db_session, redis_mock: RedisClient):
    user = User(phone="+923003009999", status="active")
    db_session.add(user)
    await db_session.flush()
    notification = Notification(
        user_id=user.id,
        source_event="billing.installment_due_d1",
        category="billing",
        priority="high",
        title="Reminder",
        body="Your installment is due",
        status="dispatching",
        idempotency_key="retry-test-multi-channel",
        channels_requested=["sms", "whatsapp"],
        template_vars={},
    )
    db_session.add(notification)
    await db_session.flush()
    due = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(NotificationDispatch(notification_id=notification.id, channel="sms", status="retrying", next_retry_at=due))
    db_session.add(NotificationDispatch(notification_id=notification.id, channel="whatsapp", status="retrying", next_retry_at=due))
    await db_session.commit()

    await retry_worker.process_retry_queue()

    from src.config import settings
    queued = await redis_mock.redis.lrange(settings.NOTIFICATION_QUEUE_KEY, 0, -1)
    assert [int(v) for v in queued] == [notification.id]
