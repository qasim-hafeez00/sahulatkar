"""
Tests for PaymentWebhookConsumer.

GAP-09: Gateway's /api/v1/webhooks/payment/* endpoints enqueue a normalized
envelope to sk:queue:payment_webhook and nothing consumed it. This worker is
the consumer half of that handoff — these tests verify it actually confirms
down payments and issues VCNs from queued jobs, for every gateway shape
Gateway can enqueue.
"""
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from sk_shared.constants import QueueName
from src.models.outbox import OutboxEvent
from src.workers.payment_webhook_consumer import DLQ_KEY, PaymentWebhookConsumer

pytestmark = pytest.mark.asyncio


async def test_handle_jazzcash_success_confirms_and_queues_issue(db_session, redis_mock, test_user, seed_signed_order, monkeypatch):
    monkeypatch.setattr("src.config.settings.JAZZCASH_MERCHANT_ID", "MC12345")
    monkeypatch.setattr("src.config.settings.JAZZCASH_PASSWORD", "secret-pw")

    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    worker = PaymentWebhookConsumer(redis=redis_mock)
    raw = {
        "pp_TxnRefNo": "jc_txn_1",
        "pp_Amount": "130000",
        "pp_ResponseCode": "000",
        "order_id": order.id,
    }

    await worker._handle(db_session, {"gateway": "jazzcash", "raw": raw})
    await db_session.flush()

    result = await db_session.execute(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["order_id"] == order.id
    assert events[0].payload["amount_pkr"] == "1300"


async def test_handle_jazzcash_failed_response_code_is_ignored(db_session, redis_mock, test_user, seed_signed_order, monkeypatch):
    monkeypatch.setattr("src.config.settings.JAZZCASH_MERCHANT_ID", "MC12345")
    monkeypatch.setattr("src.config.settings.JAZZCASH_PASSWORD", "secret-pw")

    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    worker = PaymentWebhookConsumer(redis=redis_mock)
    raw = {
        "pp_TxnRefNo": "jc_txn_2",
        "pp_Amount": "130000",
        "pp_ResponseCode": "134",  # failure
        "order_id": order.id,
    }

    await worker._handle(db_session, {"gateway": "jazzcash", "raw": raw})
    await db_session.flush()

    result = await db_session.execute(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
    assert result.scalars().all() == []


async def test_handle_safepay_success_confirms_and_queues_issue(db_session, redis_mock, test_user, seed_signed_order, monkeypatch):
    monkeypatch.setattr("src.config.settings.SAFEPAY_API_KEY", "sp-key")
    monkeypatch.setattr("src.config.settings.SAFEPAY_API_SECRET", "sp-secret")

    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    worker = PaymentWebhookConsumer(redis=redis_mock)
    raw = {
        "gateway_txn_id": "sp_txn_1",
        "amount_pkr": "1300",
        "status": "PAID",
        "order_id": order.id,
    }

    await worker._handle(db_session, {"gateway": "safepay", "raw": raw})
    await db_session.flush()

    result = await db_session.execute(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].payload["order_id"] == order.id


async def test_handle_safepay_non_paid_status_is_ignored(db_session, redis_mock, test_user, seed_signed_order, monkeypatch):
    monkeypatch.setattr("src.config.settings.SAFEPAY_API_KEY", "sp-key")
    monkeypatch.setattr("src.config.settings.SAFEPAY_API_SECRET", "sp-secret")

    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    worker = PaymentWebhookConsumer(redis=redis_mock)
    raw = {"gateway_txn_id": "sp_txn_2", "amount_pkr": "1300", "status": "pending", "order_id": order.id}

    await worker._handle(db_session, {"gateway": "safepay", "raw": raw})
    await db_session.flush()

    result = await db_session.execute(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
    assert result.scalars().all() == []


async def test_handle_missing_order_id_does_not_raise(db_session, redis_mock, monkeypatch):
    monkeypatch.setattr("src.config.settings.SAFEPAY_API_KEY", "sp-key")
    monkeypatch.setattr("src.config.settings.SAFEPAY_API_SECRET", "sp-secret")

    worker = PaymentWebhookConsumer(redis=redis_mock)
    raw = {"gateway_txn_id": "sp_txn_3", "amount_pkr": "1300", "status": "PAID"}  # no order_id

    # Must not raise — just logs and returns.
    await worker._handle(db_session, {"gateway": "safepay", "raw": raw})


async def test_handle_stripe_delegates_to_vcn_orchestrator(db_session, redis_mock):
    worker = PaymentWebhookConsumer(redis=redis_mock)
    raw = {"type": "issuing_card.updated", "data": {"object": {"card": "ic_test_123"}}}

    with patch("src.orchestration.vcn_orchestrator.VcnOrchestrator.handle_stripe_event", new=AsyncMock()) as mock_handle:
        await worker._handle(db_session, {"gateway": "stripe", "raw": raw})

    mock_handle.assert_awaited_once_with("issuing_card.updated", {"card": "ic_test_123"})


async def test_handle_unknown_gateway_is_dropped_without_raising(db_session, redis_mock):
    worker = PaymentWebhookConsumer(redis=redis_mock)
    await worker._handle(db_session, {"gateway": "unknown_provider", "raw": {}})


async def test_process_handles_invalid_json_without_crashing(redis_mock):
    worker = PaymentWebhookConsumer(redis=redis_mock)
    # Must not raise
    await worker._process(b"not-valid-json!!!")


async def test_process_dlq_after_max_retries(redis_mock, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "DLQ_MAX_RETRIES", 0)

    worker = PaymentWebhookConsumer(redis=redis_mock)
    with patch.object(PaymentWebhookConsumer, "_handle", new=AsyncMock(side_effect=RuntimeError("boom"))):
        payload = json.dumps({"gateway": "jazzcash", "raw": {}, "_retry_count": 0}).encode("utf-8")
        await worker._process(payload)

    dlq_len = await redis_mock.redis.llen(DLQ_KEY)
    assert dlq_len == 1
    queue_len = await redis_mock.redis.llen(QueueName.PAYMENT_WEBHOOK)
    assert queue_len == 0


async def test_process_requeues_with_backoff_before_max_retries(redis_mock, monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "DLQ_MAX_RETRIES", 3)

    async def _fake_sleep(_):
        return None

    monkeypatch.setattr("src.workers.payment_webhook_consumer.asyncio.sleep", _fake_sleep)

    worker = PaymentWebhookConsumer(redis=redis_mock)
    with patch.object(PaymentWebhookConsumer, "_handle", new=AsyncMock(side_effect=RuntimeError("boom"))):
        payload = json.dumps({"gateway": "jazzcash", "raw": {}, "_retry_count": 0}).encode("utf-8")
        await worker._process(payload)

    queue_len = await redis_mock.redis.llen(QueueName.PAYMENT_WEBHOOK)
    assert queue_len == 1
    requeued = json.loads(await redis_mock.redis.rpop(QueueName.PAYMENT_WEBHOOK))
    assert requeued["_retry_count"] == 1
