import pytest

pytestmark = pytest.mark.asyncio


async def test_down_payment_initiates_safepay_checkout(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    response = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={"order_id": order.id, "method": "safepay", "amount_pkr": 1300},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["payment_session_url"].startswith("https://sandbox.safepay.pk/checkout-link")


async def test_down_payment_rejects_when_contract_missing(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id, status="contracts_pending")

    response = await client.post(
        "/api/v1/payments/down-payment",
        headers={"Authorization": f"Bearer {token}"},
        json={"order_id": order.id, "method": "jazzcash", "amount_pkr": 1300},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "MURABAHA_NOT_SIGNED"