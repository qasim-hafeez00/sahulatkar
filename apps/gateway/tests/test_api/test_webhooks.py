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


async def test_jazzcash_webhook_dedup_via_db_fallback_when_redis_key_missing(
    client: AsyncClient, db_session, redis_mock
):
    """MEDIUM fix: webhook dedup previously relied solely on a 24h Redis
    SETNX marker with no fallback. This proves the DB-backed second layer
    actually catches a duplicate when Redis has no marker for the key --
    simulated directly by pre-seeding processed_webhook_events (NOT by
    going through Redis first), so this only passes if _enqueue_webhook
    genuinely checks the DB and not just Redis.
    """
    from datetime import datetime, timezone

    from sk_shared.constants import QueueName
    from sk_shared.models.webhook import ProcessedWebhookEvent

    idempotency_key = "jazzcash:TXN-DB-DEDUP-1"
    db_session.add(
        ProcessedWebhookEvent(
            idempotency_key=idempotency_key,
            gateway="jazzcash",
            processed_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    # Confirm Redis genuinely has no marker for this key before the call.
    assert await redis_mock.redis.get(f"sk:webhook:processed:{idempotency_key}") is None

    raw_body = b'{"pp_ResponseCode":"000","pp_TxnRefNo":"TXN-DB-DEDUP-1"}'
    response = await client.post(
        "/api/v1/webhooks/payment/jazzcash",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-JazzCash-Signature": _signature(settings.JAZZCASH_WEBHOOK_SECRET, raw_body),
        },
    )
    assert response.status_code == 200

    # The duplicate must NOT have been re-enqueued for processing.
    queue_len = await redis_mock.redis.llen(QueueName.PAYMENT_WEBHOOK)
    assert queue_len == 0