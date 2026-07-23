"""
Tests for src/workers/notification_consumer.py.

The consumer's own responsibility is queue orchestration (BRPOP off the
notification queue, bounded concurrency via a semaphore, graceful shutdown,
tolerating a single dispatch failure without killing the loop) — not the
per-channel dispatch logic itself (covered by
tests/test_services/test_dispatch_retry.py). So dispatch_notification is
faked here rather than exercised end-to-end through real channel providers.
"""
import asyncio
import contextlib
from contextlib import asynccontextmanager

import pytest

from sk_shared.redis_client import RedisClient
from src.config import settings
from src.services.notification_service import NotificationService
from src.workers import notification_consumer

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _patch_worker_infra(monkeypatch, db_session, redis_mock: RedisClient):
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(notification_consumer, "SessionLocal", _session_cm)
    monkeypatch.setattr(notification_consumer, "get_redis_client", lambda *a, **k: redis_mock)
    notification_consumer._shutdown = False
    yield
    notification_consumer._shutdown = True


async def _run_until(predicate, timeout: float = 3.0, interval: float = 0.02) -> None:
    task = asyncio.create_task(notification_consumer.run_consumer())
    try:
        elapsed = 0.0
        while not predicate() and elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
    finally:
        notification_consumer._shutdown = True
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_pulls_queued_id_and_dispatches_it(monkeypatch, redis_mock: RedisClient):
    dispatched_ids: list[int] = []

    async def fake_dispatch(self, notification_id: int) -> None:
        dispatched_ids.append(notification_id)

    monkeypatch.setattr(NotificationService, "dispatch_notification", fake_dispatch)
    await redis_mock.redis.lpush(settings.NOTIFICATION_QUEUE_KEY, "42")

    await _run_until(lambda: dispatched_ids)

    assert dispatched_ids == [42]


async def test_a_failed_dispatch_does_not_kill_the_loop(monkeypatch, redis_mock: RedisClient):
    dispatched_ids: list[int] = []

    async def flaky_dispatch(self, notification_id: int) -> None:
        if notification_id == 1:
            raise RuntimeError("boom")
        dispatched_ids.append(notification_id)

    monkeypatch.setattr(NotificationService, "dispatch_notification", flaky_dispatch)
    # lpush both up front; BRPOP drains right-to-left, so "1" (pushed first,
    # now leftmost) pops before "2" — the loop must survive id 1 raising and
    # still go on to process id 2 from the same queue.
    await redis_mock.redis.lpush(settings.NOTIFICATION_QUEUE_KEY, "1")
    await redis_mock.redis.lpush(settings.NOTIFICATION_QUEUE_KEY, "2")

    await _run_until(lambda: dispatched_ids)

    assert dispatched_ids == [2]
