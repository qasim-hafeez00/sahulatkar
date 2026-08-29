from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.workers.execution_reaper_worker import ExecutionReaperWorker


class _SingleSessionFactory:
    """Same pattern as test_price_staleness_worker.py's helper -- swaps the
    worker's `SessionLocal()` for a fixed test session so `_reap_once()` can
    be exercised without a real DB connection pool."""

    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_execution_reaper_worker_reaps_stuck_execution(monkeypatch, db_session, redis_mock, make_execution):
    """HIGH-02: the scheduled sweep must call through to
    ExecutionReaperService and actually move a stuck 'running' row to a
    terminal state -- not just no-op."""
    monkeypatch.setattr(settings, "CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS", 300)
    monkeypatch.setattr("src.workers.execution_reaper_worker.SessionLocal", _SingleSessionFactory(db_session))

    stuck = await make_execution(
        db_session,
        order_id=701,
        vcn_id=801,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=6000),
    )
    await db_session.commit()

    worker = ExecutionReaperWorker(redis_mock)
    await worker._reap_once()

    await db_session.refresh(stuck)
    assert stuck.status in {"failed", "hitl_escalated"}
    assert stuck.failure_type == "worker_timeout"


@pytest.mark.asyncio
async def test_execution_reaper_worker_leaves_in_flight_execution_alone(monkeypatch, db_session, redis_mock, make_execution):
    monkeypatch.setattr(settings, "CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS", 300)
    monkeypatch.setattr("src.workers.execution_reaper_worker.SessionLocal", _SingleSessionFactory(db_session))

    in_flight = await make_execution(
        db_session,
        order_id=702,
        vcn_id=802,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    await db_session.commit()

    worker = ExecutionReaperWorker(redis_mock)
    await worker._reap_once()

    await db_session.refresh(in_flight)
    assert in_flight.status == "running"
