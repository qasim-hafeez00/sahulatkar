"""
test_orders.py — Full user order flow: initiate → offer → accept
"""
import pytest
from httpx import AsyncClient
from sk_shared.models.order import Order

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_initiate_order_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/orders/initiate", json={"product_url": "https://example.com/product/1"})
    assert r.status_code in {401, 403}


async def test_initiate_order_blocked_when_kyc_not_active(client: AsyncClient, test_user):
    """Users with status != 'active' are blocked by the KYC hard gate."""
    user, token = test_user
    assert user.status == "pending_kyc"
    r = await client.post(
        "/api/v1/orders/initiate",
        json={"product_url": "https://example.com/product/1"},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "KYC_NOT_APPROVED"


async def test_initiate_order_succeeds_for_active_user(client: AsyncClient, test_user, db_session):
    """An active user can initiate an order."""
    from sk_shared.models.auth import User
    from sqlalchemy import update
    user, token = test_user
    # Activate the user and give credit (GAP-13/17 alignment)
    await db_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(status="active", credit_limit=100000, available_credit=100000)
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/orders/initiate",
        json={"product_url": "https://daraz.pk/product/123"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert "order_id" in body
    assert body["status"] == "processing"


async def test_get_order_tracking_returns_shipment(client: AsyncClient, test_user, db_session):
    from sk_shared.models.delivery import Shipment, TrackingEvent
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(update(User).where(User.id == user.id).values(status="active"))
    await db_session.commit()

    order = Order(user_id=user.id, status="delivery_pending", total_amount=1000, product_description="https://test.com")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    shipment = Shipment(
        order_id=order.id,
        courier_name="TCS",
        tracking_number="TRK-123",
        status="in_transit",
    )
    db_session.add(shipment)
    await db_session.commit()
    await db_session.refresh(shipment)

    event = TrackingEvent(
        shipment_id=shipment.id,
        event_code="IN_TRANSIT",
        event_description="Parcel is moving",
        location_city="Lahore",
        event_time=shipment.created_at,
    )
    db_session.add(event)
    await db_session.commit()

    r = await client.get(f"/api/v1/orders/{order.id}/tracking", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["shipment"]["tracking_number"] == "TRK-123"
    assert body["shipment"]["last_event"]["event_code"] == "IN_TRANSIT"


async def test_get_order_offer_returns_pending_when_no_product(client: AsyncClient, test_user, db_session):
    """Offer endpoint returns 'pending' when product extraction hasn't completed."""
    from sk_shared.models.auth import User
    from sk_shared.models.order import Order
    from sqlalchemy import update
    user, token = test_user
    await db_session.execute(update(User).where(User.id == user.id).values(status="active"))
    await db_session.commit()

    order = Order(user_id=user.id, status="url_received", total_amount=0, product_description="https://test.com")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.get(f"/api/v1/orders/{order.id}/offer", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


async def test_list_orders_empty_for_new_user(client: AsyncClient, test_user):
    _, token = test_user
    r = await client.get("/api/v1/orders", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []


async def test_get_order_detail_404_for_wrong_user(client: AsyncClient, test_user):
    _, token = test_user
    r = await client.get("/api/v1/orders/999999", headers=_auth(token))
    assert r.status_code == 404
    assert r.json()["detail"] == "ORDER_NOT_FOUND"


async def test_accept_offer_conflict_when_status_wrong(client: AsyncClient, test_user, db_session):
    from sk_shared.models.order import Order
    user, token = test_user
    # Order in a terminal state
    order = Order(user_id=user.id, status="contracts_signed", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        f"/api/v1/orders/{order.id}/accept",
        json={"installment_count": 3},
        headers=_auth(token),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "OFFER_NOT_READY"
