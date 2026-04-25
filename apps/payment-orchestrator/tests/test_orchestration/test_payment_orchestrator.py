"""
Tests for PaymentOrchestrator state machine.

Covers:
  - initiate_payment creates workflow in INITIATED state
  - Duplicate idempotency key returns existing workflow (no double-charge)
  - mark_pending transitions INITIATED → PENDING
  - confirm_payment transitions INITIATED → CAPTURED (sync) and PENDING → CAPTURED (async)
  - mark_failed transitions correctly
  - expire_session transitions INITIATED/PENDING → EXPIRED
  - Illegal state transitions raise PaymentWorkflowError
  - Outbox events are queued on state transitions
"""
from decimal import Decimal

import pytest

from src.orchestration.payment_orchestrator import PaymentOrchestrator
from src.state.payment_workflow import PaymentStatus, PaymentWorkflowError

pytestmark = pytest.mark.asyncio


async def _make_orchestrator(db_session):
    return PaymentOrchestrator(db_session)


async def test_initiate_payment_creates_workflow(db_session, test_user):
    """initiate_payment creates a new PaymentWorkflow in INITIATED state."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=1,
        user_id=user.id,
        amount_pkr=Decimal("1300.00"),
        gateway="safepay",
        idempotency_key="test-idem-001",
    )
    await db_session.commit()

    assert workflow.id is not None
    assert workflow.status == PaymentStatus.INITIATED
    assert workflow.order_id == 1
    assert workflow.gateway == "safepay"
    assert workflow.amount_pkr == Decimal("1300.00")


async def test_initiate_payment_idempotent_returns_existing(db_session, test_user):
    """Calling initiate_payment twice with the same key returns the same workflow."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    w1 = await orch.initiate_payment(
        order_id=1, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="jazzcash", idempotency_key="test-idem-002",
    )
    await db_session.commit()

    w2 = await orch.initiate_payment(
        order_id=1, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="jazzcash", idempotency_key="test-idem-002",
    )

    assert w1.id == w2.id, "Idempotency broken — two different workflows created"


async def test_mark_pending_transitions_initiated_to_pending(db_session, test_user):
    """mark_pending correctly transitions INITIATED → PENDING."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=2, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="safepay", idempotency_key="test-idem-003",
    )
    await db_session.flush()

    updated = await orch.mark_pending(workflow.id, "sp_txn_abc123")
    assert updated.status == PaymentStatus.PENDING
    assert updated.gateway_session_id == "sp_txn_abc123"


async def test_confirm_payment_from_initiated_for_sync_gateway(db_session, test_user):
    """INITIATED → CAPTURED is valid for sync gateways (JazzCash direct charge)."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=3, user_id=user.id, amount_pkr=Decimal("975.00"),
        gateway="jazzcash", idempotency_key="test-idem-004",
    )
    await db_session.flush()

    captured = await orch.confirm_payment(
        workflow.id, "jc_txn_xyz", {"status": "success"}
    )
    assert captured.status == PaymentStatus.CAPTURED
    assert captured.confirmed_at is not None


async def test_confirm_payment_from_pending_for_async_gateway(db_session, test_user):
    """PENDING → CAPTURED is valid for async gateways (SafePay webhook)."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=4, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="safepay", idempotency_key="test-idem-005",
    )
    await db_session.flush()

    await orch.mark_pending(workflow.id, "sp_session_001")
    captured = await orch.confirm_payment(workflow.id, "sp_txn_confirmed", {"status": "PAID"})
    assert captured.status == PaymentStatus.CAPTURED


async def test_mark_failed_transitions_correctly(db_session, test_user):
    """mark_failed transitions INITIATED → FAILED and records error."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=5, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="jazzcash", idempotency_key="test-idem-006",
    )
    await db_session.flush()

    failed = await orch.mark_failed(workflow.id, "Gateway timeout")
    assert failed.status == PaymentStatus.FAILED
    assert failed.last_error == "Gateway timeout"
    assert failed.attempt_count == 1


async def test_expire_session_from_initiated(db_session, test_user):
    """expire_session transitions INITIATED → EXPIRED."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=6, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="raast", idempotency_key="test-idem-007",
    )
    await db_session.flush()

    await orch.expire_session(workflow.id)
    assert workflow.status == PaymentStatus.EXPIRED


async def test_expire_session_from_pending(db_session, test_user):
    """expire_session transitions PENDING → EXPIRED (async gateway timeout)."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=7, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="safepay", idempotency_key="test-idem-008",
    )
    await db_session.flush()
    await orch.mark_pending(workflow.id, "sp_session_expired")
    await orch.expire_session(workflow.id)

    assert workflow.status == PaymentStatus.EXPIRED


async def test_illegal_transition_captured_to_initiated_raises(db_session, test_user):
    """CAPTURED → INITIATED is an illegal transition — must raise PaymentWorkflowError."""
    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=8, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="jazzcash", idempotency_key="test-idem-009",
    )
    await db_session.flush()
    await orch.confirm_payment(workflow.id, "jc_ok", {"status": "success"})

    # Attempting CAPTURED → INITIATED (not allowed in transition matrix)
    with pytest.raises(PaymentWorkflowError):
        from src.state.payment_workflow import validate_transition
        validate_transition(PaymentStatus.CAPTURED, PaymentStatus.INITIATED)


async def test_illegal_transition_pending_to_initiated_raises(db_session, test_user):
    """PENDING → INITIATED is illegal — cannot go back to initiated from pending."""
    with pytest.raises(PaymentWorkflowError):
        from src.state.payment_workflow import validate_transition
        validate_transition(PaymentStatus.PENDING, PaymentStatus.INITIATED)


async def test_outbox_event_queued_on_payment_confirmation(db_session, test_user):
    """confirm_payment must queue a payment.confirmed outbox event."""
    from sqlalchemy import select
    from src.models.outbox import OutboxEvent

    user, _ = test_user
    orch = await _make_orchestrator(db_session)

    workflow = await orch.initiate_payment(
        order_id=9, user_id=user.id, amount_pkr=Decimal("1300.00"),
        gateway="jazzcash", idempotency_key="test-idem-010",
    )
    await db_session.flush()
    await orch.confirm_payment(workflow.id, "jc_txn_outbox", {"status": "success"})
    await db_session.flush()

    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_name == "payment.confirmed")
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["payload"]["workflow_id"] == workflow.id
