"""
Tests for PaymentInitiateConsumer.

Gateway's customer-facing payment endpoints enqueue to sk:queue:payment_initiate
and nothing consumed it — meaning no down payment, installment payment, or
refund request ever reached a real payment gateway in production. These tests
verify the consumer actually drives the gateway call and updates the same
PaymentTransaction row Gateway created.
"""
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from sk_shared.constants import QueueName
from sk_shared.models.payment import PaymentTransaction
from src.models.outbox import OutboxEvent
from src.models.refund_workflow import RefundWorkflow
from src.workers.payment_initiate_consumer import DLQ_KEY, PaymentInitiateConsumer

pytestmark = pytest.mark.asyncio


async def test_handle_down_payment_sync_gateway_confirms_and_queues_vcn(
    db_session, redis_mock, test_user, seed_signed_order
):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    txn = PaymentTransaction(
        order_id=order.id, user_id=user.id, amount=Decimal("1300"), currency="PKR",
        gateway="jazzcash", transaction_type="down_payment", status="initiated",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(return_value={"gateway_txn_id": "jc_init_1"})
        mock_factory.return_value = adapter

        await worker._handle(db_session, {
            "event": "payment.initiate_requested",
            "payment_id": txn.id,
            "order_id": order.id,
            "user_id": user.id,
            "amount": "1300",
            "gateway": "jazzcash",
        })

    await db_session.refresh(txn)
    assert txn.status == "success"
    assert txn.gateway_txn_id == "jc_init_1"

    vcn_issue = await db_session.scalar(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
    assert vcn_issue is not None

    # Regression: confirm_down_payment() looks up this PaymentTransaction by
    # status IN (initiated, pending) to queue the event that tells Gateway to
    # advance Order.status past CONTRACTS_SIGNED. If txn.status is flipped to
    # "success" before that lookup runs, it silently finds nothing and
    # Gateway is never notified even though the charge succeeded.
    gateway_notify = await db_session.scalar(
        select(OutboxEvent).where(OutboxEvent.event_name == "gateway.payment_confirmed")
    )
    assert gateway_notify is not None
    assert gateway_notify.payload["payment_id"] == txn.id


async def test_handle_down_payment_async_gateway_stays_pending(
    db_session, redis_mock, test_user, seed_signed_order
):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    txn = PaymentTransaction(
        order_id=order.id, user_id=user.id, amount=Decimal("1300"), currency="PKR",
        gateway="safepay", transaction_type="down_payment", status="initiated",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch("src.services.routing_engine.GatewayRoutingEngine.select_gateway", new=AsyncMock(return_value="safepay")), \
         patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(return_value={"gateway_txn_id": "sp_init_1", "payment_url": "https://pay.example/sp"})
        mock_factory.return_value = adapter

        await worker._handle(db_session, {
            "event": "payment.initiate_requested",
            "payment_id": txn.id,
            "order_id": order.id,
            "user_id": user.id,
            "amount": "1300",
            "gateway": "safepay",
        })

    await db_session.refresh(txn)
    assert txn.status == "pending"
    assert txn.gateway_txn_id == "sp_init_1"

    vcn_issue = await db_session.scalar(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
    assert vcn_issue is None  # not issued until the webhook confirms


async def test_handle_down_payment_gateway_failure_marks_transaction_failed(
    db_session, redis_mock, test_user, seed_signed_order
):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    txn = PaymentTransaction(
        order_id=order.id, user_id=user.id, amount=Decimal("1300"), currency="PKR",
        gateway="jazzcash", transaction_type="down_payment", status="initiated",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(side_effect=RuntimeError("gateway down"))
        mock_factory.return_value = adapter

        await worker._handle(db_session, {
            "event": "payment.initiate_requested",
            "payment_id": txn.id,
            "order_id": order.id,
            "user_id": user.id,
            "amount": "1300",
            "gateway": "jazzcash",
        })

    await db_session.refresh(txn)
    assert txn.status == "failed"
    assert "gateway down" in txn.failure_message


async def test_handle_down_payment_skips_already_processed_transaction(
    db_session, redis_mock, test_user, seed_signed_order
):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    txn = PaymentTransaction(
        order_id=order.id, user_id=user.id, amount=Decimal("1300"), currency="PKR",
        gateway="jazzcash", transaction_type="down_payment", status="success",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        await worker._handle(db_session, {
            "event": "payment.initiate_requested",
            "payment_id": txn.id,
            "order_id": order.id,
            "user_id": user.id,
            "amount": "1300",
        })
        mock_factory.assert_not_called()


async def test_handle_installment_success_publishes_installment_paid_event(
    db_session, redis_mock, test_user, seed_order_with_loan
):
    from sk_shared.models.payment import Installment

    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)
    installment = (await db_session.execute(
        select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number.asc())
    )).scalars().first()

    txn = PaymentTransaction(
        loan_id=loan.id, installment_id=installment.id, user_id=user.id,
        amount=Decimal("975"), currency="PKR", gateway="jazzcash",
        transaction_type="installment_repayment", status="initiated",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory, \
         patch.object(redis_mock, "publish", new=AsyncMock()) as mock_publish:
        adapter = AsyncMock()
        adapter.initiate_payment = AsyncMock(return_value={"gateway_txn_id": "jc_inst_1"})
        mock_factory.return_value = adapter

        await worker._handle(db_session, {
            "event": "payment.installment_requested",
            "payment_id": txn.id,
            "installment_id": installment.id,
            "loan_id": loan.id,
            "user_id": user.id,
            "amount": "975",
            "gateway": "jazzcash",
        })

    await db_session.refresh(txn)
    assert txn.status == "success"
    assert txn.gateway_txn_id == "jc_inst_1"

    mock_publish.assert_awaited_once()
    channel, message = mock_publish.await_args[0]
    assert channel == "sk:events:payment.installment_paid"
    body = json.loads(message)
    assert body["payload"]["installment_id"] == installment.id


async def test_handle_refund_calls_refund_orchestrator(db_session, redis_mock, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    original_txn = PaymentTransaction(
        order_id=order.id, user_id=user.id, amount=Decimal("5200"), currency="PKR",
        gateway="jazzcash", gateway_txn_id="jc_original_1", transaction_type="down_payment", status="success",
    )
    db_session.add(original_txn)
    await db_session.commit()

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch("src.adapters.factory.GatewayAdapterFactory.get") as mock_factory:
        adapter = AsyncMock()
        adapter.refund = AsyncMock(return_value={"gateway_refund_id": "jc_ref_1", "status": "success"})
        mock_factory.return_value = adapter

        await worker._handle(db_session, {
            "event": "payment.refund_requested",
            "order_id": order.id,
            "user_id": user.id,
            "amount": "5200",
            "reason": "customer_requested: changed my mind",
        })

    refund = await db_session.scalar(select(RefundWorkflow).where(RefundWorkflow.order_id == order.id))
    assert refund is not None
    assert refund.amount_pkr == Decimal("5200")


async def test_handle_refund_drops_when_no_successful_payment_found(db_session, redis_mock, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    # Must not raise even though there's nothing to refund against.
    await worker._handle(db_session, {
        "event": "payment.refund_requested",
        "order_id": order.id,
        "user_id": user.id,
        "amount": "5200",
        "reason": "customer_requested: no payment on record",
    })

    refund = await db_session.scalar(select(RefundWorkflow).where(RefundWorkflow.order_id == order.id))
    assert refund is None


async def test_handle_unknown_event_is_dropped_without_raising(db_session, redis_mock):
    worker = PaymentInitiateConsumer(redis=redis_mock)
    await worker._handle(db_session, {"event": "loan.restructure_requested", "order_id": 1})


async def test_process_dlq_after_max_retries(redis_mock, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "DLQ_MAX_RETRIES", 0)

    worker = PaymentInitiateConsumer(redis=redis_mock)
    with patch.object(PaymentInitiateConsumer, "_handle", new=AsyncMock(side_effect=RuntimeError("boom"))):
        payload = json.dumps({"event": "payment.initiate_requested", "_retry_count": 0}).encode("utf-8")
        await worker._process(payload)

    assert await redis_mock.redis.llen(DLQ_KEY) == 1
    assert await redis_mock.redis.llen(QueueName.PAYMENT_INITIATE) == 0
