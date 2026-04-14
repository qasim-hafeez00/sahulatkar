import asyncio

import pytest
from sqlalchemy import select

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue

from src.services.checkout_agent import CheckoutAgentService
from src.workers.checkout_consumer import CheckoutConsumer
from sk_shared.models.product import Product
from sk_shared.models.order import Order


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
    product = Product(name="Test", url="https://merchant.example/product", canonical_url="https://merchant.example/product", currency="PKR", cost_price=100)
    db_session.add(product)
    await db_session.flush()

    order = Order(user_id=1, product_id=product.id, total_amount=100, status="confirmed")
    db_session.add(order)
    await db_session.flush()

    from sk_shared.models.payment import VirtualCard
    from datetime import datetime, timezone, timedelta
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

    service = CheckoutAgentService(db_session, redis_mock)
    execution = await service.queue_job(
        order_id=order.id,
        vcn_id=vcn.id,
    )

    consumer = CheckoutConsumer()

    original_process_job = CheckoutAgentService.process_job

    async def process_and_stop(self, payload: dict) -> None:
        await original_process_job(self, payload)
        consumer.running = False
        
    async def mock_run_checkout(*args, **kwargs):
        return {"merchant_order_id": f"SK-{order.id}", "merchant_order_url": "https://merchant.example/success"}

    monkeypatch.setattr("src.workers.checkout_consumer.get_redis_client", lambda *_args, **_kwargs: redis_mock)
    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.workers.checkout_consumer.CheckoutAgentService.process_job", process_and_stop)
    monkeypatch.setattr("src.services.checkout_agent.CheckoutAgentService._run_playwright_checkout", mock_run_checkout)

    await asyncio.wait_for(consumer.run(), timeout=2)

    refreshed = await db_session.scalar(select(PurchaseExecution).where(PurchaseExecution.id == execution.id))
    assert refreshed is not None
    assert refreshed.status == "succeeded"
    assert refreshed.merchant_order_id == f"SK-{order.id}"


@pytest.mark.asyncio
async def test_checkout_consumer_escalates_hitl_on_forced_failure(monkeypatch, db_session, redis_mock):
    product = Product(name="Fail", url="https://f.com", currency="PKR", cost_price=1)
    db_session.add(product)
    await db_session.flush()
    order = Order(user_id=1, product_id=product.id, total_amount=1, status="confirmed")
    db_session.add(order)
    await db_session.flush()

    service = CheckoutAgentService(db_session, redis_mock)
    execution = await service.queue_job(order_id=order.id, vcn_id=8102, force_failure=True)

    consumer = CheckoutConsumer()

    original_process_job = CheckoutAgentService.process_job

    async def process_and_stop(self, payload: dict) -> None:
        await original_process_job(self, payload)
        consumer.running = False

    monkeypatch.setattr("src.workers.checkout_consumer.get_redis_client", lambda *_args, **_kwargs: redis_mock)
    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.workers.checkout_consumer.CheckoutAgentService.process_job", process_and_stop)

    await asyncio.wait_for(consumer.run(), timeout=2)

    refreshed = await db_session.scalar(select(PurchaseExecution).where(PurchaseExecution.id == execution.id))
    assert refreshed is not None
    assert refreshed.status == "hitl_escalated"

    hitl = await db_session.scalar(select(HitlQueue).where(HitlQueue.execution_id == execution.id))
    assert hitl is not None
    assert hitl.status == "pending"


@pytest.mark.asyncio
async def test_checkout_consumer_idle_path_closes_redis(monkeypatch, db_session, redis_mock):
    consumer = CheckoutConsumer()
    closed = {"called": False}

    async def fake_brpop(_queue_name, timeout=5):
        consumer.running = False
        return None

    async def fake_close() -> None:
        closed["called"] = True

    monkeypatch.setattr(redis_mock.redis, "brpop", fake_brpop)
    monkeypatch.setattr(redis_mock, "close", fake_close)
    monkeypatch.setattr("src.workers.checkout_consumer.get_redis_client", lambda *_args, **_kwargs: redis_mock)
    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))

    await asyncio.wait_for(consumer.run(), timeout=2)

    assert closed["called"] is True
