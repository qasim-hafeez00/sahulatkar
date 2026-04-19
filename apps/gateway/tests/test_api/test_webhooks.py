import pytest
from httpx import AsyncClient
import hmac
import hashlib

from src.config import settings

pytestmark = pytest.mark.asyncio


def _signature(secret: str | None, raw_body: bytes) -> str:
    assert secret is not None
    return hmac.new(secret.encode(), raw_body, digestmod=hashlib.sha256).hexdigest()


async def test_jazzcash_webhook_receives_payload(client: AsyncClient):
    payload = {"pp_ResponseCode": "000", "pp_TxnRefNo": "TXN-001"}
    raw_body = b'{"pp_ResponseCode":"000","pp_TxnRefNo":"TXN-001"}'
    response = await client.post(
        "/api/v1/webhooks/payment/jazzcash",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-JazzCash-Signature": _signature(settings.JAZZCASH_WEBHOOK_SECRET, raw_body),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["gateway"] == "jazzcash"


async def test_safepay_webhook_receives_payload(client: AsyncClient):
    raw_body = b'{"payment_id":123,"status":"confirmed"}'
    response = await client.post(
        "/api/v1/webhooks/payment/safepay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-SafePay-Signature": _signature(settings.SAFEPAY_WEBHOOK_SECRET, raw_body),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["gateway"] == "safepay"


async def test_webhook_payload_too_large_rejected(client: AsyncClient):
    oversized = {"blob": "x" * (1_048_576 + 200)}
    response = await client.post(
        "/api/v1/webhooks/payment/jazzcash",
        json=oversized,
        headers={"X-JazzCash-Signature": "bogus"},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "WEBHOOK_PAYLOAD_TOO_LARGE"


async def test_webhook_invalid_signature_rejected(client: AsyncClient):
    raw_body = b'{"pp_ResponseCode":"000","pp_TxnRefNo":"TXN-INVALID"}'
    response = await client.post(
        "/api/v1/webhooks/payment/jazzcash",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-JazzCash-Signature": "deadbeef",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "INVALID_WEBHOOK_SIGNATURE"


async def test_webhook_wrong_content_type_rejected(client: AsyncClient):
    raw_body = b'{"pp_ResponseCode":"000","pp_TxnRefNo":"TXN-002"}'
    response = await client.post(
        "/api/v1/webhooks/payment/jazzcash",
        content=raw_body,
        headers={
            "Content-Type": "text/plain",
            "X-JazzCash-Signature": _signature(settings.JAZZCASH_WEBHOOK_SECRET, raw_body),
        },
    )
    assert response.status_code == 415
    assert response.json()["detail"] == "UNSUPPORTED_CONTENT_TYPE: application/json required"