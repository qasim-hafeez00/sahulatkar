import pytest
from sqlalchemy import select

from sk_shared.constants import OrderState
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.product import Merchant, Product

from src.services.delivery_events import apply_delivery_confirmed_envelope, apply_delivery_status_envelope
from tests.conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


async def _seed_order(user_id: int, status: str) -> Order:
    async with TestingSessionLocal() as session:
        merchant = Merchant(name="Delivery Merchant", normalized_name="delivery-merchant", domain="delivery.example.com")
        session.add(merchant)
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            name="Delivery Product",
            url="https://delivery.example.com/p/1",
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


def _make_envelope(event: str, order_id: int, new_status: str | None = None) -> dict:
    payload = {"order_id": order_id}
    if new_status is not None:
        payload["new_status"] = new_status
    return {"event": event, "payload": payload}


async def test_apply_delivery_status_envelope_transitions_to_in_transit(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.DELIVERY_PENDING)
    envelope = _make_envelope("delivery.status_changed", order.id, "in_transit")

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_status_envelope(session, envelope)
        assert changed is True

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        assert db_order.status == OrderState.IN_TRANSIT
        history = (await session.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id))).all()
        assert len(history) == 1
        assert history[0].to_status == OrderState.IN_TRANSIT


async def test_apply_delivery_confirmed_envelope_transitions_to_delivered(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.IN_TRANSIT)
    envelope = _make_envelope("delivery.confirmed", order.id)

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_confirmed_envelope(session, envelope)
        assert changed is True

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        assert db_order.status == OrderState.DELIVERED


async def test_apply_delivery_status_envelope_ignores_unknown_status(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.DELIVERY_PENDING)
    envelope = _make_envelope("delivery.status_changed", order.id, "returned")

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_status_envelope(session, envelope)
        assert changed is False

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        assert db_order.status == OrderState.DELIVERY_PENDING


async def test_apply_delivery_status_envelope_idempotent(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.IN_TRANSIT)
    envelope = _make_envelope("delivery.status_changed", order.id, "in_transit")

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_status_envelope(session, envelope)
        assert changed is False

    async with TestingSessionLocal() as session:
        history = (await session.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id))).all()
        assert len(history) == 0
