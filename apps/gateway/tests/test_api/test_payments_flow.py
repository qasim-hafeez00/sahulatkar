"""
test_payments_flow.py — Down payment initiation and payment schedule retrieval.
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_down_payment_requires_auth(client: AsyncClient):
    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": 1, "method": "safepay", "amount_pkr": "1000.00"},
    )
    assert r.status_code in {401, 403}


async def test_down_payment_blocked_when_not_contracts_signed(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(user_id=user.id, status="offer_accepted", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "jazzcash", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "CONTRACTS_NOT_SIGNED"


async def test_down_payment_amount_mismatch_rejected(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "easypaisa", "amount_pkr": "5000.00"},
        headers=_auth(token),
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "DOWN_PAYMENT_AMOUNT_MISMATCH"


async def test_down_payment_succeeds_with_correct_amount(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "raast", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "initiated"
    assert "payment_id" in body


async def test_down_payment_invalid_method_rejected(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "paypal", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 422  # Pydantic pattern validation


async def test_payment_schedule_404_when_no_loan(client: AsyncClient, test_user):
    _, token = test_user
    r = await client.get("/api/v1/payments/schedule/999999", headers=_auth(token))
    assert r.status_code == 404
    assert r.json()["detail"] == "LOAN_NOT_FOUND"


async def test_vcn_blocked_without_down_payment(client: AsyncClient, test_user, db_session):
    """VCN must be blocked when order status is CONTRACTS_SIGNED (not DOWN_PAYMENT_RECEIVED)."""
    from sk_shared.models.order import Order
    user, token = test_user
    order = Order(user_id=user.id, status="contracts_signed", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "DOWN_PAYMENT_NOT_CONFIRMED"
