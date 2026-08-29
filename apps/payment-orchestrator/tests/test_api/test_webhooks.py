"""
Tests for gateway webhook endpoints.
Target: 15 test cases
"""
import json

import pytest

from src.config import settings
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.safepay import SafepayClient

from tests.conftest import TestingSessionLocal
from src.models.outbox import OutboxEvent
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


# ── SafePay Webhooks ──────────────────────────────────────────────────────────

async def test_safepay_webhook_processes_paid_event(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "gateway_txn_id": "sp_abc123", "status": "PAID"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET).sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/safepay",
        content=body,
        headers={"X-Safepay-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    
    # VCN issue should be queued in Outbox
    async with TestingSessionLocal() as session:
        result = await session.execute(select(OutboxEvent).where(OutboxEvent.event_name == "vcn.issue"))
        events = result.scalars().all()
        assert len(events) >= 1


async def test_safepay_webhook_rejects_invalid_signature(client):
    body = json.dumps({"order_id": 1, "amount_pkr": 1300, "status": "PAID"}).encode()
    resp = await client.post(
        "/api/v1/webhooks/safepay",
        content=body,
        headers={"X-Safepay-Signature": "bad-signature"},
    )
    assert resp.status_code == 401


async def test_safepay_webhook_deduplicates_repeated_events(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "gateway_txn_id": "sp_dedup_test", "status": "PAID"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET).sign_payload(body)

    resp1 = await client.post("/api/v1/webhooks/safepay", content=body, headers={"X-Safepay-Signature": sig})
    resp2 = await client.post("/api/v1/webhooks/safepay", content=body, headers={"X-Safepay-Signature": sig})

    assert resp1.json()["status"] == "ok"
    assert resp2.json()["status"] == "duplicate"


async def test_safepay_webhook_deduplicates_retry_with_different_body_same_txn_id(client, test_user, redis_mock, seed_signed_order):
    """PO-CRIT-04 regression: dedup must key on the gateway's own stable
    gateway_txn_id, not a hash of the raw body+signature. A legitimate
    gateway retry is not guaranteed to be byte-identical to the original
    delivery (e.g. an added metadata field) -- under the old hash-based key
    this second, differently-bodied delivery would NOT have been recognized
    as a duplicate and would have double-processed."""
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    gw_client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET)

    payload1 = {"order_id": order.id, "amount_pkr": 1300, "gateway_txn_id": "sp_retry_test", "status": "PAID"}
    body1 = json.dumps(payload1).encode()
    sig1 = gw_client.sign_payload(body1)

    # Same logical event re-delivered with an extra field -- different bytes
    # (and therefore a different body+signature hash), same gateway_txn_id.
    payload2 = {**payload1, "retry_attempt": 2}
    body2 = json.dumps(payload2).encode()
    sig2 = gw_client.sign_payload(body2)

    resp1 = await client.post("/api/v1/webhooks/safepay", content=body1, headers={"X-Safepay-Signature": sig1})
    resp2 = await client.post("/api/v1/webhooks/safepay", content=body2, headers={"X-Safepay-Signature": sig2})

    assert resp1.json()["status"] == "ok"
    assert resp2.json()["status"] == "duplicate"


async def test_safepay_webhook_ignores_non_paid_status(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "status": "FAILED"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET, webhook_secret=settings.SAFEPAY_WEBHOOK_SECRET).sign_payload(body)

    resp = await client.post("/api/v1/webhooks/safepay", content=body, headers={"X-Safepay-Signature": sig})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── JazzCash Webhooks ─────────────────────────────────────────────────────────

async def test_jazzcash_webhook_processes_success_code(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "pp_TxnRefNo": "jc_xyz", "pp_ResponseCode": "000"}
    body = json.dumps(payload).encode()
    sig = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD).sign_payload(body)

    resp = await client.post("/api/v1/webhooks/jazzcash", content=body, headers={"X-JazzCash-Signature": sig})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_jazzcash_webhook_rejects_bad_signature(client):
    body = json.dumps({"order_id": 1, "amount_pkr": 1300, "pp_ResponseCode": "000"}).encode()
    resp = await client.post(
        "/api/v1/webhooks/jazzcash",
        content=body,
        headers={"X-JazzCash-Signature": "invalid"},
    )
    assert resp.status_code == 401


async def test_jazzcash_webhook_ignores_non_000_response(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "pp_ResponseCode": "111"}
    body = json.dumps(payload).encode()
    sig = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD).sign_payload(body)

    resp = await client.post("/api/v1/webhooks/jazzcash", content=body, headers={"X-JazzCash-Signature": sig})
    assert resp.json()["status"] == "ignored"


# ── Raast Webhooks ────────────────────────────────────────────────────────────

async def test_raast_webhook_processes_confirmed_transfer(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {
        "transaction_id": "raast_test123",
        "order_id": order.id,
        "amount_pkr": "1300",
        "status": "success",
        "reference_no": "SBP-REF-001",
    }
    body = json.dumps(payload).encode()
    raast_client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )
    sig = raast_client._sign_payload(body)

    resp = await client.post("/api/v1/webhooks/raast", content=body, headers={"X-Raast-Signature": sig})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_raast_webhook_rejects_invalid_signature(client):
    body = json.dumps({"transaction_id": "raast_abc", "order_id": 1, "amount_pkr": "1300", "status": "success"}).encode()
    resp = await client.post(
        "/api/v1/webhooks/raast",
        content=body,
        headers={"X-Raast-Signature": "bad-sig"},
    )
    assert resp.status_code == 401


async def test_raast_webhook_ignores_failed_transfer(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"transaction_id": "raast_fail", "order_id": order.id, "amount_pkr": "1300", "status": "failed"}
    body = json.dumps(payload).encode()
    raast_client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )
    sig = raast_client._sign_payload(body)

    resp = await client.post("/api/v1/webhooks/raast", content=body, headers={"X-Raast-Signature": sig})
    assert resp.json()["status"] == "ignored"


async def test_raast_webhook_deduplicates(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"transaction_id": "raast_dedup", "order_id": order.id, "amount_pkr": "1300", "status": "success"}
    body = json.dumps(payload).encode()
    raast_client = RaastClient(
        api_key=settings.RAAST_API_KEY,
        api_secret=settings.RAAST_API_SECRET,
        merchant_iban=settings.RAAST_MERCHANT_IBAN,
    )
    sig = raast_client._sign_payload(body)

    r1 = await client.post("/api/v1/webhooks/raast", content=body, headers={"X-Raast-Signature": sig})
    r2 = await client.post("/api/v1/webhooks/raast", content=body, headers={"X-Raast-Signature": sig})
    assert r1.json()["status"] == "ok"
    assert r2.json()["status"] == "duplicate"
