"""
Tests for the async refund-completion webhooks (P1: wires
RefundOrchestrator.settle_refund up to a real completion path, mirroring the
existing payment-confirmation webhooks in this same file).
"""
import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from src.config import settings
from src.models.outbox import OutboxEvent
from src.models.refund_workflow import RefundStatus, RefundWorkflow
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.safepay import SafepayClient
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _seed_pending_refund(order_id: int, user_id: int, refund_reference: str) -> RefundWorkflow:
    async with TestingSessionLocal() as session:
        refund = RefundWorkflow(
            original_payment_workflow_id=1,
            order_id=order_id,
            user_id=user_id,
            refund_reference=refund_reference,
            amount_pkr=Decimal("500.00"),
            reason="test pending refund",
            status=RefundStatus.PENDING,
            gateway="safepay",
        )
        session.add(refund)
        await session.commit()
        await session.refresh(refund)
        return refund


async def test_safepay_refund_webhook_settles_pending_refund(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    refund = await _seed_pending_refund(order.id, user.id, "refund-webhook-safepay-001")

    payload = {"refund_reference": refund.refund_reference, "gateway_refund_id": "sp_rfnd_confirmed", "status": "success"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/safepay/refund",
        content=body,
        headers={"X-Safepay-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    async with TestingSessionLocal() as session:
        updated = await session.get(RefundWorkflow, refund.id)
        assert updated.status == RefundStatus.SETTLED
        assert updated.gateway_refund_id == "sp_rfnd_confirmed"
        assert updated.settled_at is not None

        events = (await session.execute(
            select(OutboxEvent).where(OutboxEvent.event_name == "payment.refund_settled")
        )).scalars().all()
        assert len(events) >= 1


async def test_safepay_refund_webhook_rejects_invalid_signature(client):
    body = json.dumps({"refund_reference": "whatever", "status": "success"}).encode()
    resp = await client.post(
        "/api/v1/webhooks/safepay/refund",
        content=body,
        headers={"X-Safepay-Signature": "bad-signature"},
    )
    assert resp.status_code == 401


async def test_safepay_refund_webhook_ignores_unknown_reference(client):
    payload = {"refund_reference": "does-not-exist", "gateway_refund_id": "sp_x", "status": "success"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/safepay/refund",
        content=body,
        headers={"X-Safepay-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


async def test_jazzcash_refund_webhook_settles_pending_refund(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    refund = await _seed_pending_refund(order.id, user.id, "refund-webhook-jazzcash-001")

    payload = {"refund_reference": refund.refund_reference, "gateway_refund_id": "jc_rfnd_confirmed", "status": "success"}
    body = json.dumps(payload).encode()
    sig = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD).sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/jazzcash/refund",
        content=body,
        headers={"X-JazzCash-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    async with TestingSessionLocal() as session:
        updated = await session.get(RefundWorkflow, refund.id)
        assert updated.status == RefundStatus.SETTLED


async def test_raast_refund_webhook_settles_pending_refund(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    refund = await _seed_pending_refund(order.id, user.id, "refund-webhook-raast-001")

    payload = {"refund_reference": refund.refund_reference, "gateway_refund_id": "raast_rfnd_confirmed", "status": "success"}
    body = json.dumps(payload).encode()
    raast_client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )
    sig = raast_client._sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/raast/refund",
        content=body,
        headers={"X-Raast-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    async with TestingSessionLocal() as session:
        updated = await session.get(RefundWorkflow, refund.id)
        assert updated.status == RefundStatus.SETTLED


async def test_refund_webhook_deduplicates_repeated_events(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    refund = await _seed_pending_refund(order.id, user.id, "refund-webhook-dedup-001")

    payload = {"refund_reference": refund.refund_reference, "gateway_refund_id": "sp_rfnd_dedup", "status": "success"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    resp1 = await client.post("/api/v1/webhooks/safepay/refund", content=body, headers={"X-Safepay-Signature": sig})
    resp2 = await client.post("/api/v1/webhooks/safepay/refund", content=body, headers={"X-Safepay-Signature": sig})

    assert resp1.json()["status"] == "ok"
    assert resp2.json()["status"] == "duplicate"


async def test_refund_webhook_ignores_non_success_status(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)
    refund = await _seed_pending_refund(order.id, user.id, "refund-webhook-notyet-001")

    payload = {"refund_reference": refund.refund_reference, "status": "processing"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/safepay/refund",
        content=body,
        headers={"X-Safepay-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    async with TestingSessionLocal() as session:
        updated = await session.get(RefundWorkflow, refund.id)
        assert updated.status == RefundStatus.PENDING
