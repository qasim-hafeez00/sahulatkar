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

pytestmark = pytest.mark.asyncio


# ── SafePay Webhooks ──────────────────────────────────────────────────────────

async def test_safepay_webhook_processes_paid_event(client, test_user, redis_mock, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "gateway_txn_id": "sp_abc123", "status": "PAID"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    resp = await client.post(
        "/api/v1/webhooks/safepay",
        content=body,
        headers={"X-Safepay-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    # VCN issue should be queued
    assert await redis_mock.redis.llen("sk:queue:vcn_issue") >= 1


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
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    resp1 = await client.post("/api/v1/webhooks/safepay", content=body, headers={"X-Safepay-Signature": sig})
    resp2 = await client.post("/api/v1/webhooks/safepay", content=body, headers={"X-Safepay-Signature": sig})

    assert resp1.json()["status"] == "ok"
    assert resp2.json()["status"] == "duplicate"


async def test_safepay_webhook_ignores_non_paid_status(client, test_user, seed_signed_order):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "status": "FAILED"}
    body = json.dumps(payload).encode()
    sig = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

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
