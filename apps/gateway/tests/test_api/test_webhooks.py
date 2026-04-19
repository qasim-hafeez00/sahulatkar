import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_jazzcash_webhook_receives_payload(client: AsyncClient):
    response = await client.post(
        "/api/v1/webhooks/payment/jazzcash",
        json={"pp_ResponseCode": "000", "pp_TxnRefNo": "TXN-001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["gateway"] == "jazzcash"


async def test_safepay_webhook_receives_payload(client: AsyncClient):
    response = await client.post(
        "/api/v1/webhooks/payment/safepay",
        json={"payment_id": 123, "status": "confirmed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["gateway"] == "safepay"