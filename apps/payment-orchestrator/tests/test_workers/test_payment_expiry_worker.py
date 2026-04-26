from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.models.outbox import OutboxEvent
from src.models.payment_workflow import PaymentWorkflow
from src.state.payment_workflow import PaymentStatus
from src.workers.payment_expiry_worker import PaymentSessionExpiryWorker
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _create_workflow(session, *, status: PaymentStatus, expires_delta_minutes: int) -> PaymentWorkflow:
    wf = PaymentWorkflow(
        order_id=123,
        user_id=456,
        idempotency_key=f"idem-{status.value}-{expires_delta_minutes}-{datetime.now(timezone.utc).timestamp()}",
        status=status,
        gateway="safepay",
        amount_pkr=Decimal("1300.00"),
        session_expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_delta_minutes),
    )
    session.add(wf)
    await session.commit()
    await session.refresh(wf)
    return wf


async def test_expiry_worker_sweeps_initiated_and_pending(monkeypatch):
    import src.workers.payment_expiry_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    async with TestingSessionLocal() as db:
        initiated = await _create_workflow(db, status=PaymentStatus.INITIATED, expires_delta_minutes=-5)
        pending = await _create_workflow(db, status=PaymentStatus.PENDING, expires_delta_minutes=-5)
        captured = await _create_workflow(db, status=PaymentStatus.CAPTURED, expires_delta_minutes=-5)

    worker = PaymentSessionExpiryWorker()
    await worker.sweep_expired_sessions()

    async with TestingSessionLocal() as db:
        i2 = await db.get(PaymentWorkflow, initiated.id)
        p2 = await db.get(PaymentWorkflow, pending.id)
        c2 = await db.get(PaymentWorkflow, captured.id)
        assert i2.status == PaymentStatus.EXPIRED
        assert p2.status == PaymentStatus.EXPIRED
        assert c2.status == PaymentStatus.CAPTURED


async def test_expiry_worker_ignores_unexpired_sessions(monkeypatch):
    import src.workers.payment_expiry_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    async with TestingSessionLocal() as db:
        wf = await _create_workflow(db, status=PaymentStatus.INITIATED, expires_delta_minutes=30)

    worker = PaymentSessionExpiryWorker()
    await worker.sweep_expired_sessions()

    async with TestingSessionLocal() as db:
        wf2 = await db.get(PaymentWorkflow, wf.id)
        assert wf2.status == PaymentStatus.INITIATED


async def test_expiry_worker_queues_session_expired_events(monkeypatch):
    import src.workers.payment_expiry_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    async with TestingSessionLocal() as db:
        _ = await _create_workflow(db, status=PaymentStatus.INITIATED, expires_delta_minutes=-5)
        _ = await _create_workflow(db, status=PaymentStatus.PENDING, expires_delta_minutes=-5)

    worker = PaymentSessionExpiryWorker()
    await worker.sweep_expired_sessions()

    async with TestingSessionLocal() as db:
        result = await db.execute(
            select(OutboxEvent).where(OutboxEvent.event_name == "payment.session_expired")
        )
        events = result.scalars().all()
        assert len(events) == 2


async def test_expiry_worker_stop_sets_flag_false():
    worker = PaymentSessionExpiryWorker()
    assert worker.is_running is True
    worker.stop()
    assert worker.is_running is False
