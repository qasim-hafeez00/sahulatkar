import pytest

pytestmark = pytest.mark.asyncio


async def test_vcn_issue_hard_gate(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    blocked = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200, "merchant_domain": "example.com"},
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "active"


async def test_vcn_issue_blocks_without_signed_contract(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id, status="contracts_pending")

    response = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200, "merchant_domain": "example.com"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "MURABAHA_NOT_SIGNED"