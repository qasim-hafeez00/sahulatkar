import json

import pytest

from src.config import settings
from src.services.jazzcash import JazzCashClient
from src.services.safepay import SafepayClient

pytestmark = pytest.mark.asyncio


async def test_safepay_webhook_confirms_down_payment(client, test_user, redis_mock, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    payload = {"order_id": order.id, "amount_pkr": 1300, "gateway_txn_id": "sp_123", "status": "PAID"}
    body = json.dumps(payload).encode("utf-8")
    signature = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET).sign_payload(body)

    response = await client.post(
        "/api/v1/webhooks/safepay",
        content=body,
        headers={"X-Safepay-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert await redis_mock.redis.llen("sk:queue:vcn_issue") == 1


async def test_jazzcash_webhook_rejects_bad_signature(client):
    body = json.dumps({"order_id": 1, "amount_pkr": 1300, "pp_ResponseCode": "000"}).encode("utf-8")
    response = await client.post(
        "/api/v1/webhooks/jazzcash",
        content=body,
        headers={"X-JazzCash-Signature": "bad-signature"},
    )

    assert response.status_code == 401