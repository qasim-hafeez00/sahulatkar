"""
Tests for src/workers/scheduled_worker.py.

Phase 2: zero test coverage, and the worker was completely broken — it
queried ScheduledNotification.scheduled_for and read scheduled.template_vars,
neither of which exist on the model (the real columns are fire_at and
payload). Every sweep would raise AttributeError on the very first query,
so "scheduled_for was never honoured" (per this file's own docstring) was
true for the wrong reason: not because the worker didn't exist, but because
it never ran without crashing. Fixed the field names and covered here.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from sk_shared.models.auth import User
from sk_shared.models.notification import Notification, ScheduledNotification
from sk_shared.redis_client import RedisClient

from src.workers import scheduled_worker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _patch_worker_infra(monkeypatch, db_session, redis_mock: RedisClient):
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(scheduled_worker, "SessionLocal", _session_cm)
    monkeypatch.setattr(scheduled_worker, "get_redis_client", lambda *a, **k: redis_mock)


async def _seed_user(db_session, suffix: int) -> User:
    user = User(phone=f"+9230020{suffix:05d}", status="active")
    db_session.add(user)
    await db_session.flush()
    return user


async def _seed_scheduled(db_session, **kwargs) -> int:
    """Insert via Core (not the ORM) to bypass ScheduledNotification's
    before_insert validator, which rejects a past fire_at — correct for
    admin-facing scheduling, but a real "due" row is exactly one whose
    future fire_at has since elapsed, which this reconstructs directly."""
    result = await db_session.execute(
        insert(ScheduledNotification.__table__).values(**kwargs).returning(ScheduledNotification.id)
    )
    await db_session.commit()
    return result.scalar_one()


async def test_fires_due_scheduled_notification(db_session):
    user = await _seed_user(db_session, 1)
    due_id = await _seed_scheduled(
        db_session,
        user_id=user.id,
        event_type="billing.installment_due_d1",
        payload={"installment_amount": "975"},
        fire_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        idempotency_key="sched-1",
    )

    stats = await scheduled_worker.fire_scheduled_notifications()

    assert stats == {"found": 1, "fired": 1, "errors": 0, "skipped_cancelled": 0}
    due = await db_session.get(ScheduledNotification, due_id)
    assert due.fired_at is not None

    notification = await db_session.scalar(
        select(Notification).where(Notification.idempotency_key == f"scheduled-{due_id}")
    )
    assert notification is not None
    assert notification.template_vars == {"installment_amount": "975"}


async def test_ignores_not_yet_due_scheduled_notification(db_session):
    user = await _seed_user(db_session, 2)
    future_id = await _seed_scheduled(
        db_session,
        user_id=user.id,
        event_type="billing.installment_due_d1",
        payload={},
        fire_at=datetime.now(timezone.utc) + timedelta(hours=1),
        idempotency_key="sched-2",
    )

    stats = await scheduled_worker.fire_scheduled_notifications()

    assert stats["found"] == 0
    future = await db_session.get(ScheduledNotification, future_id)
    assert future.fired_at is None


async def test_ignores_already_fired_and_cancelled(db_session):
    user = await _seed_user(db_session, 3)
    now = datetime.now(timezone.utc)
    await _seed_scheduled(
        db_session, user_id=user.id, event_type="x", payload={}, fire_at=now - timedelta(minutes=5),
        idempotency_key="sched-3", fired_at=now - timedelta(minutes=1),
    )
    await _seed_scheduled(
        db_session, user_id=user.id, event_type="x", payload={}, fire_at=now - timedelta(minutes=5),
        idempotency_key="sched-4", cancelled_at=now - timedelta(minutes=1),
    )

    stats = await scheduled_worker.fire_scheduled_notifications()

    assert stats["found"] == 0
