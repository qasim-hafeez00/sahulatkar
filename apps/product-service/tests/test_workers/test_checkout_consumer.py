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

from src.services.checkout import CheckoutAgentService
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

    payload = {"execution_id": str(execution.uuid)}

    consumer = CheckoutConsumer(max_concurrency=1)

    async def mock_run_checkout(*args, **kwargs):
        return {"merchant_order_id": f"SK-{order.id}", "merchant_order_url": "https://m.com/success"}

    async def mock_verify_charge(*args, **kwargs):
        return True

    async def mock_fetch_vcn_credentials(*args, **kwargs):
        return {"pan": "4242424242424242", "cvv": "123", "expiry_month": "12", "expiry_year": "2027"}

    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))
    monkeypatch.setattr("src.services.checkout.form_filler.CheckoutFormFiller.run_checkout", mock_run_checkout)
    monkeypatch.setattr("src.services.checkout.vcn_verifier.VcnVerifier.verify_charge", mock_verify_charge)
    monkeypatch.setattr("src.services.checkout.agent.CheckoutAgentService._fetch_vcn_credentials", mock_fetch_vcn_credentials)

    await consumer._process_with_sem(payload, redis_mock)

    await db_session.refresh(execution)
    assert execution.status == "pending_verification"
    
    # Verify enqueued job for VCN worker
    items = await redis_mock.redis.lrange(QueueName.VCN_VERIFICATION, 0, -1)
    assert len(items) == 1


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
    consumer = CheckoutConsumer(max_concurrency=1)

    monkeypatch.setattr("src.workers.checkout_consumer.SessionLocal", _SingleSessionFactory(db_session))

    await consumer._process_with_sem(payload, redis_mock)

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


@pytest.mark.asyncio
async def test_checkout_consumer_invalid_payload_goes_to_dlq(db_session, redis_mock):
    consumer = CheckoutConsumer(max_concurrency=1)

    payload = {"order_id": 1}  # missing execution_id
    await consumer._process_with_sem(payload, redis_mock)

    # GAP-A FIX: DLQ key is now correctly "sk:queue:dlq:checkout" (not the
    # doubled "sk:queue:dlq:sk:queue:checkout" that the old code produced).
    dlq_items = await redis_mock.redis.lrange("sk:queue:dlq:checkout", 0, -1)
    assert len(dlq_items) == 1
    assert "Missing execution_id" in dlq_items[0].decode("utf-8")


@pytest.mark.asyncio
async def test_checkout_consumer_duplicate_processing_is_skipped(monkeypatch, db_session, redis_mock):
    execution = PurchaseExecution(
        order_id=1,
        vcn_id=1,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    await db_session.commit()

    called = {"count": 0}

    async def fake_process_job(self, payload_arg):
        called["count"] += 1

    monkeypatch.setattr("src.services.checkout.agent.CheckoutAgentService.process_job", fake_process_job)

    consumer = CheckoutConsumer(max_concurrency=1)
    payload = {"execution_id": str(execution.uuid)}

    # Simulate another worker already holding the lock.
    await redis_mock.redis.set(f"sk:checkout:processing:{execution.uuid}", "1", ex=600)
    await consumer._process_with_sem(payload, redis_mock)

    assert called["count"] == 0
