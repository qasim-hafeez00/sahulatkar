from datetime import datetime, timezone, timedelta
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.models.product import Product
from src.services.checkout import CheckoutAgentService
from src.services.checkout.agent import CheckoutCancelledError


async def _seed_order_vcn(db_session):
    product = Product(name="T", url="https://m.com/p", currency="PKR", cost_price=100)
    db_session.add(product)
    await db_session.flush()

    order = Order(user_id=1, product_id=product.id, total_amount=100, status="confirmed")
    db_session.add(order)
    await db_session.flush()

    vcn = VirtualCard(
        order_id=order.id,
        user_id=1,
        issuer="MOCK",
        issuer_card_id="VCN-1",
        masked_number="4111********1111",
        card_expiry=datetime.now(timezone.utc).date() + timedelta(days=30),
        authorized_amount=100.0,
        loaded_amount=100.0,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(vcn)
    await db_session.flush()
    await db_session.commit()
    return order, vcn


@pytest.mark.asyncio
async def test_queue_job_reuses_active_execution(db_session, redis_mock):
    order, vcn = await _seed_order_vcn(db_session)
    service = CheckoutAgentService(db_session, redis_mock)

    first = await service.queue_job(order_id=order.id, vcn_id=vcn.id)
    second = await service.queue_job(order_id=order.id, vcn_id=vcn.id)

    assert str(first.uuid) == str(second.uuid)


@pytest.mark.asyncio
async def test_process_job_sets_pending_verification_payload_when_unverified(db_session, redis_mock):
    """process_job should mark as pending_verification if the verifier returns False."""
    order, vcn = await _seed_order_vcn(db_session)

    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    service = CheckoutAgentService(db_session, redis_mock)

    # Mock the internal components of the orchestrator
    service.form_filler.run_checkout = AsyncMock(return_value={
        "merchant_order_id": "SK-1",
        "merchant_order_url": "https://m.com/order"
    })
    service.verifier.verify_charge = AsyncMock(return_value=False)
    service._fetch_vcn_credentials = AsyncMock(return_value={
        "pan": "4242424242424242", "cvv": "123", "expiry_month": "12", "expiry_year": "2027",
    })

    await service.process_job({"execution_id": str(execution.uuid)})

    await db_session.refresh(execution)
    assert execution.status == "pending_verification"
    
    # Check that job was enqueued for VCN verification worker.
    from sk_shared.constants import QueueName
    # lpush means it's at the head (right side for brpop, left side for lrange 0)
    # Actually brpop pops from RIGHT, so let's check the list.
    items = await redis_mock.redis.lrange(QueueName.VCN_VERIFICATION, 0, -1)
    assert len(items) == 1
    payload = json.loads(items[0].decode("utf-8"))
    assert payload["execution_id"] == str(execution.uuid)
    assert payload["vcn_id"] == vcn.id


@pytest.mark.asyncio
async def test_cancel_job_noop_for_terminal_state(db_session, redis_mock):
    order, vcn = await _seed_order_vcn(db_session)
    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="succeeded",
        step_reached="receipt",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    service = CheckoutAgentService(db_session, redis_mock)
    await service.cancel_job(execution.uuid)

    await db_session.refresh(execution)
    assert execution.status == "succeeded"


@pytest.mark.asyncio
async def test_mark_failed_escalates_hitl(db_session, redis_mock):
    order, vcn = await _seed_order_vcn(db_session)
    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="running",
        step_reached="submit_order",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    service = CheckoutAgentService(db_session, redis_mock)
    await service._mark_failed(execution, "checkout_changed", "broken selector")

    await db_session.refresh(execution)
    assert execution.status == "hitl_escalated"

    hitl = await db_session.scalar(select(HitlQueue).where(HitlQueue.order_id == execution.order_id))
    assert hitl is not None


@pytest.mark.asyncio
async def test_process_job_stops_on_mid_flight_cancellation_during_step(db_session, redis_mock):
    """HIGH-03: a cancel_job() call (or an order.cancelled event) can flip a
    PurchaseExecution's status to 'cancelled' from a different DB
    session/request while process_job is still mid-Playwright-run. The
    per-step check inside emit_step (form_filler's step-callback) must
    notice this on the very next step and raise CheckoutCancelledError, and
    the row must never be clobbered back to 'succeeded'."""
    order, vcn = await _seed_order_vcn(db_session)
    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    service = CheckoutAgentService(db_session, redis_mock)
    service._fetch_vcn_credentials = AsyncMock(return_value={
        "pan": "4242424242424242", "cvv": "123", "expiry_month": "12", "expiry_year": "2027",
    })

    raised: dict = {}

    async def fake_run_checkout(**kwargs):
        # Simulate the external cancellation landing on this execution's row
        # mid-flight (a different DB session/request in production; same
        # session here since db_session is what CheckoutAgentService was
        # constructed with).
        execution.status = "cancelled"
        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db_session.commit()

        # process_job wired emit_step in as form_filler's step callback
        # before calling run_checkout -- invoke it the way the real
        # CheckoutFormFiller would on its next Playwright step.
        try:
            await service.form_filler._step_callback("payment_injection")
        except CheckoutCancelledError as e:
            raised["error"] = e
            raise
        # Should never be reached -- the interrupt above must fire first.
        return {"merchant_order_id": "SK-1", "merchant_order_url": "https://m.com/order"}

    service.form_filler.run_checkout = fake_run_checkout

    await service.process_job({"execution_id": str(execution.uuid)})

    assert isinstance(raised.get("error"), CheckoutCancelledError)

    await db_session.refresh(execution)
    assert execution.status != "succeeded"
    assert execution.merchant_order_id is None


@pytest.mark.asyncio
async def test_process_job_stops_on_cancellation_right_before_succeeded_commit(db_session, redis_mock):
    """HIGH-03 (final race-window check): a cancellation that lands after
    the last step check (order_confirmed) but before process_job writes
    'succeeded' must still be caught -- process_job re-checks the persisted
    status once more right before that commit."""
    order, vcn = await _seed_order_vcn(db_session)
    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    service = CheckoutAgentService(db_session, redis_mock)
    service._fetch_vcn_credentials = AsyncMock(return_value={
        "pan": "4242424242424242", "cvv": "123", "expiry_month": "12", "expiry_year": "2027",
    })

    async def fake_run_checkout(**kwargs):
        # From the form filler's point of view, the checkout ran to a
        # completely normal, successful finish (no step ever saw
        # 'cancelled') -- but the cancellation lands in the gap between
        # run_checkout returning and process_job's own commit of
        # status='succeeded'.
        execution.status = "cancelled"
        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db_session.commit()
        return {"merchant_order_id": "SK-1", "merchant_order_url": "https://m.com/order"}

    service.form_filler.run_checkout = fake_run_checkout

    await service.process_job({"execution_id": str(execution.uuid)})

    await db_session.refresh(execution)
    assert execution.status != "succeeded"
    assert execution.merchant_order_id is None
