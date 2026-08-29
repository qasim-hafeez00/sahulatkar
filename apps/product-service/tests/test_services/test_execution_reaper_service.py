from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from sk_shared.models.hitl import HitlQueue

from src.config import settings
from src.services.execution_reaper_service import ExecutionReaperService


@pytest.mark.asyncio
async def test_is_stuck_true_for_running_past_timeout(db_session, make_execution, monkeypatch):
    """HIGH-02: a PurchaseExecution stuck at status='running' longer than
    CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS (its owning worker crashed/was
    killed mid-job) must be identified as stuck."""
    monkeypatch.setattr(settings, "CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS", 300)

    execution = await make_execution(
        db_session,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=600),
    )
    await db_session.commit()

    assert ExecutionReaperService.is_stuck(execution) is True


@pytest.mark.asyncio
async def test_is_stuck_false_for_recently_started_running_execution(db_session, make_execution, monkeypatch):
    """A genuinely in-flight execution (started well within the timeout
    window) must NOT be considered stuck -- a legitimately slow-but-alive
    checkout (retries, proxy negotiation, slow merchant site) shouldn't be
    reaped out from under itself."""
    monkeypatch.setattr(settings, "CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS", 300)

    execution = await make_execution(
        db_session,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    await db_session.commit()

    assert ExecutionReaperService.is_stuck(execution) is False


@pytest.mark.asyncio
async def test_is_stuck_false_for_non_running_status(db_session, make_execution, monkeypatch):
    """Only 'running' rows are ever candidates -- a terminal status is never
    reaped regardless of how old started_at is."""
    monkeypatch.setattr(settings, "CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS", 300)

    execution = await make_execution(
        db_session,
        status="failed",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=6000),
    )
    await db_session.commit()

    assert ExecutionReaperService.is_stuck(execution) is False


@pytest.mark.asyncio
async def test_is_stuck_false_when_started_at_is_none(db_session, make_execution):
    """An execution with no started_at recorded (e.g. seeded directly in a
    test, or genuinely just transitioned to 'running' this instant) has no
    elapsed time to judge it by -- never treated as stuck."""
    execution = await make_execution(db_session, status="running", step_reached="payment_injection")
    await db_session.commit()

    assert ExecutionReaperService.is_stuck(execution) is False


@pytest.mark.asyncio
async def test_reap_marks_stuck_execution_hitl_escalated_when_enabled(db_session, make_execution, monkeypatch):
    """.reap() moves a stuck execution to a terminal state (failed, then
    escalated to hitl_escalated when FEATURE_HITL_ESCALATION is on) and
    creates a HitlQueue entry for manual review of whether the merchant-side
    purchase actually completed before the worker died."""
    monkeypatch.setattr(settings, "FEATURE_HITL_ESCALATION", True)

    execution = await make_execution(
        db_session,
        order_id=555,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=6000),
    )
    await db_session.commit()

    service = ExecutionReaperService(db_session)
    await service.reap(execution)

    await db_session.refresh(execution)
    assert execution.status == "hitl_escalated"
    assert execution.failure_type == "worker_timeout"
    assert execution.error_detail is not None
    assert "Reaped by ExecutionReaperService" in execution.error_detail
    assert execution.completed_at is not None

    hitl = await db_session.scalar(
        select(HitlQueue).where(HitlQueue.execution_id == execution.id)
    )
    assert hitl is not None
    assert hitl.order_id == 555


@pytest.mark.asyncio
async def test_reap_marks_stuck_execution_failed_when_hitl_disabled(db_session, make_execution, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_HITL_ESCALATION", False)

    execution = await make_execution(
        db_session,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=6000),
    )
    await db_session.commit()

    service = ExecutionReaperService(db_session)
    await service.reap(execution)

    await db_session.refresh(execution)
    assert execution.status == "failed"
    assert execution.failure_type == "worker_timeout"


@pytest.mark.asyncio
async def test_reap_all_stuck_only_reaps_stuck_rows(db_session, make_execution, monkeypatch):
    monkeypatch.setattr(settings, "CHECKOUT_STUCK_RUNNING_TIMEOUT_SECONDS", 300)

    stuck = await make_execution(
        db_session,
        order_id=101,
        vcn_id=201,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=6000),
    )
    in_flight = await make_execution(
        db_session,
        order_id=102,
        vcn_id=202,
        status="running",
        step_reached="payment_injection",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    already_terminal = await make_execution(
        db_session,
        order_id=103,
        vcn_id=203,
        status="succeeded",
        step_reached="receipt",
    )
    await db_session.commit()

    service = ExecutionReaperService(db_session)
    reaped = await service.reap_all_stuck()

    reaped_ids = {e.id for e in reaped}
    assert reaped_ids == {stuck.id}

    await db_session.refresh(stuck)
    await db_session.refresh(in_flight)
    await db_session.refresh(already_terminal)
    assert stuck.status in {"failed", "hitl_escalated"}
    assert in_flight.status == "running"
    assert already_terminal.status == "succeeded"
