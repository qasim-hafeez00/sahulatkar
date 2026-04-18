import pytest
from sqlalchemy import select

from sk_shared.constants import OrderState
from sk_shared.models.order import Order
from sk_shared.models.product import Merchant, Product
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_order(user_id: int, status: str) -> Order:
    async with TestingSessionLocal() as session:
        merchant = Merchant(name="Gate Merchant", normalized_name="gate-merchant", domain="gate.example.com")
        session.add(merchant)
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            name="Gate Product",
            url="https://example.com/p/gate",
            currency="PKR",
            cost_price=5000,
            sale_price=5200,
            in_stock=True,
        )
        session.add(product)
        await session.flush()

        order = Order(
            user_id=user_id,
            product_id=product.id,
            status=status,
            total_amount=5200,
            down_payment_amount=1300,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def test_vcn_issue_blocked_until_down_payment_confirmed(client, test_user):
    user, token = test_user
    order = await _seed_order(user.id, OrderState.CONTRACTS_PENDING)

    blocked_pending = await client.post(
        "/api/v1/payments/vcn/issue",
        headers=_auth(token),
        json={"order_id": order.id},
    )
    assert blocked_pending.status_code == 403
    assert blocked_pending.json()["detail"] == "VCN_GATE_NOT_PASSED"

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        db_order.status = OrderState.CONTRACTS_SIGNED
        await session.commit()

    blocked_signed = await client.post(
        "/api/v1/payments/vcn/issue",
        headers=_auth(token),
        json={"order_id": order.id},
    )
    assert blocked_signed.status_code == 403
    assert blocked_signed.json()["detail"] == "DOWN_PAYMENT_NOT_CONFIRMED"

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        db_order.status = OrderState.DOWN_PAYMENT_RECEIVED
        await session.commit()

    allowed = await client.post(
        "/api/v1/payments/vcn/issue",
        headers=_auth(token),
        json={"order_id": order.id},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "queued"
