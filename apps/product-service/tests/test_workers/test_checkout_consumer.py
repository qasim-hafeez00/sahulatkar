import asyncio
import json
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.product import Product
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.constants import QueueName

from src.services.checkout_agent import CheckoutAgentService
from src.workers.checkout_consumer import CheckoutConsumer


class _SingleSessionFactory:
    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_checkout_consumer_processes_successful_job(monkeypatch, db_session, redis_mock):
    # Setup dependencies
    product = Product(name="Test", url="https://m.com", currency="PKR", cost_price=100)
    db_session.add(product)
    await db_session.flush()

    order = Order(user_id=1, product_id=product.id, total_amount=100, status="confirmed")
    db_session.add(order)
    await db_session.flush()

    vcn = VirtualCard(
        order_id=order.id,
        user_id=1,
        issuer="MOCK_ISSUER",
        issuer_card_id="VCN-123",
        masked_number="4111********1111",
        card_expiry=datetime.now(timezone.utc).date() + timedelta(days=30),
        authorized_amount=100.0,
        loaded_amount=100.0,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30)
    )
    db_session.add(vcn)
    await db_session.flush()

    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc)
    )
    db_session.add(execution)
    await db_session.commit()

    # Pre-load the queue
    payload = {"execution_id": str(execution.uuid)}
    await redis_mock.rpush(QueueName.CHECKOUT, json.dumps(payload))

    consumer = CheckoutConsumer(max_concurrency=1)
    processed_event = asyncio.Event()

    original_process_job = CheckoutAgentService.process_job

    async def process_and_signal(self, payload_arg: dict) -> None:
        try:
            await original_process_job(self, payload_arg)
        finally:
            processed_event.set()
            consumer.running = False

    async def mock_run_checkout(*args, **kwargs):
        return {"merchant_order_id": f"SK-{order.id}", "merchant_order_url": "https://m.com/success"}

    async def mock_verify_charge(*args, **kwargs):
        return True

    monkeypatch.setattr("src.workers.checkout_consumer.get_redis_client", lambda *_args, **_kwargs: redis_mock)
    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService.process_job", process_and_signal)
    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService._run_playwright_checkout", mock_run_checkout)
    async def mock_sleep(x):
        return

    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService._verify_vcn_charge", mock_verify_charge)
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    # Run loop
    run_task = asyncio.create_task(consumer.run())
    try:
        await asyncio.wait_for(processed_event.wait(), timeout=10)
    finally:
        consumer.running = False
        await run_task

    await db_session.refresh(execution)
    assert execution.status == "succeeded"


@pytest.mark.asyncio
async def test_checkout_consumer_escalates_hitl_on_forced_failure(monkeypatch, db_session, redis_mock):
    product = Product(name="Fail", url="https://f.com", currency="PKR", cost_price=1)
    db_session.add(product)
    await db_session.flush()
    order = Order(user_id=1, product_id=product.id, total_amount=1, status="confirmed")
    db_session.add(order)
    await db_session.flush()

    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=8102,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc)
    )
    db_session.add(execution)
    await db_session.commit()

    payload = {"execution_id": str(execution.uuid), "force_failure": True}
    await redis_mock.rpush(QueueName.CHECKOUT, json.dumps(payload))

    consumer = CheckoutConsumer(max_concurrency=1)
    processed_event = asyncio.Event()

    original_process_job = CheckoutAgentService.process_job

    async def process_and_signal(self, payload_arg: dict) -> None:
        try:
            await original_process_job(self, payload_arg)
        finally:
            processed_event.set()
            consumer.running = False

    monkeypatch.setattr("src.workers.checkout_consumer.get_redis_client", lambda *_args, **_kwargs: redis_mock)
    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService.process_job", process_and_signal)

    run_task = asyncio.create_task(consumer.run())
    try:
        await asyncio.wait_for(processed_event.wait(), timeout=10)
    finally:
        consumer.running = False
        await run_task

    await db_session.refresh(execution)
    assert execution.status == "hitl_escalated"

    hitl = await db_session.scalar(select(HitlQueue).where(HitlQueue.order_id == execution.order_id))
    assert hitl is not None
    assert hitl.status == "pending"


@pytest.mark.asyncio
async def test_checkout_consumer_idle_path_closes_redis(monkeypatch, db_session, redis_mock):
    consumer = CheckoutConsumer()
    closed = {"called": False}

    async def fake_close() -> None:
        closed["called"] = True

    # brpop returns None and stops loop
    async def mock_brpop(*args, **kwargs):
        consumer.running = False
        return None

    monkeypatch.setattr(redis_mock.redis, "brpop", mock_brpop)
    monkeypatch.setattr(redis_mock, "close", fake_close)
    monkeypatch.setattr("src.workers.checkout_consumer.get_redis_client", lambda *_args, **_kwargs: redis_mock)
    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))

    await asyncio.wait_for(consumer.run(), timeout=2)

    assert closed["called"] is True
