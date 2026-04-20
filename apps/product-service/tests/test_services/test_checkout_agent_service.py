from datetime import datetime, timezone, timedelta
import json

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.models.product import Product
from src.services.checkout_agent import CheckoutAgentService


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
async def test_process_job_sets_pending_verification_payload_when_unverified(monkeypatch, db_session, redis_mock):
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

    async def fake_checkout(*_args, **_kwargs):
        return {"merchant_order_id": "SK-1", "merchant_order_url": "https://m.com/order"}

    async def fake_verify(*_args, **_kwargs):
        return False

    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService._run_playwright_checkout", fake_checkout)
    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService._verify_vcn_charge", fake_verify)

    service = CheckoutAgentService(db_session, redis_mock)
    await service.process_job({"execution_id": str(execution.uuid)})

    await db_session.refresh(execution)
    assert execution.status == "pending_verification"
    pending_raw = await redis_mock.get(f"sk:vcn:pending_verification:{vcn.id}")
    payload = json.loads(pending_raw)
    assert payload["execution_id"] == str(execution.uuid)


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

    hitl = await db_session.scalar(select(HitlQueue).where(HitlQueue.execution_id == execution.id))
    assert hitl is not None
