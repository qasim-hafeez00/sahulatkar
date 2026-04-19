"""
test_orders.py — Full user order flow: initiate → offer → accept
"""
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy import select
from sk_shared.models.order import Order
from sk_shared.models.audit import AuditTrail

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


async def test_initiate_order_blocked_for_prohibited_category(client: AsyncClient, test_user, db_session):
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(
        update(User).where(User.id == user.id).values(status="active", credit_limit=100000, available_credit=100000)
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/orders/initiate",
        json={"product_url": "https://example.com/shop/alcohol-special-offer"},
        headers=_auth(token),
    )
    assert r.status_code == 422
    assert "PROHIBITED_PRODUCT_CATEGORY" in r.json()["detail"]


async def test_too_many_active_orders_blocked(client: AsyncClient, test_user, db_session):
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(
        update(User).where(User.id == user.id).values(status="active", credit_limit=100000, available_credit=100000)
    )
    await db_session.commit()

    active_statuses = ["url_received", "offer_presented", "offer_accepted", "contracts_pending", "contracts_signed"]
    for idx, status_value in enumerate(active_statuses, start=1):
        db_session.add(Order(user_id=user.id, status=status_value, total_amount=1000 * idx, product_description=f"seed-{idx}"))
    await db_session.commit()

    r = await client.post(
        "/api/v1/orders/initiate",
        json={"product_url": "https://example.com/products/allowed-item"},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert "TOO_MANY_ACTIVE_ORDERS" in r.json()["detail"]


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


async def test_get_order_offer_times_out_to_extraction_failed(client: AsyncClient, test_user, db_session):
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(update(User).where(User.id == user.id).values(status="active"))
    await db_session.commit()

    order = Order(user_id=user.id, status="url_received", total_amount=0, product_description="https://test.com")
    order.created_at = datetime.now(timezone.utc) - timedelta(minutes=12)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.get(f"/api/v1/orders/{order.id}/offer", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "extraction_failed"


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


async def test_accept_offer_blocked_when_credit_exceeded(client: AsyncClient, test_user, db_session):
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(
        update(User).where(User.id == user.id).values(status="active", credit_limit=1000, available_credit=0)
    )
    await db_session.commit()

    order = Order(user_id=user.id, status="offer_presented", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        f"/api/v1/orders/{order.id}/accept",
        json={"installment_count": 3},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "CREDIT_LIMIT_EXCEEDED"


async def test_accept_offer_success(client: AsyncClient, test_user, db_session):
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(
        update(User).where(User.id == user.id).values(status="active", credit_limit=10000, available_credit=10000)
    )
    await db_session.commit()

    order = Order(user_id=user.id, status="offer_presented", total_amount=9000, product_description="single-accept")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        f"/api/v1/orders/{order.id}/accept",
        json={"installment_count": 3},
        headers=_auth(token),
    )

    assert r.status_code == 200, r.text
    await db_session.refresh(order)
    assert order.status == "offer_accepted"
    assert order.installment_count == 3
    assert r.json()["installment_count"] == 3


async def test_cancel_order_offer_accepted_restores_credit(client: AsyncClient, test_user, db_session):
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(
        update(User).where(User.id == user.id).values(status="active", credit_limit=50000, available_credit=5000)
    )
    await db_session.commit()

    order = Order(user_id=user.id, status="offer_accepted", total_amount=3000, product_description="test")
    db_session.add(order)
    await db_session.commit()

    r = await client.post(f"/api/v1/orders/{order.id}/cancel", headers=_auth(token))
    assert r.status_code == 200

    await db_session.refresh(order)
    assert order.status == "cancelled"

    refreshed_user = await db_session.scalar(select(User).where(User.id == user.id))
    assert float(refreshed_user.available_credit or 0) == 8000

    audit = await db_session.scalar(
        select(AuditTrail).where(
            AuditTrail.customer_user_id == user.id,
            AuditTrail.module == "orders",
            AuditTrail.action == "order_cancelled",
            AuditTrail.target_id == order.id,
        )
    )
    assert audit is not None


async def test_concurrent_order_accept_credit_race(client: AsyncClient, test_user, db_session):
    import asyncio
    from sk_shared.models.auth import User
    from sqlalchemy import update

    user, token = test_user
    await db_session.execute(
        update(User).where(User.id == user.id).values(status="active", credit_limit=10000, available_credit=10000)
    )
    await db_session.commit()

    order = Order(user_id=user.id, status="offer_presented", total_amount=9000, product_description="race-test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    async def accept_once():
        return await client.post(
            f"/api/v1/orders/{order.id}/accept",
            json={"installment_count": 3},
            headers=_auth(token),
        )

    r1, r2 = await asyncio.gather(accept_once(), accept_once())
    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200, (
        r1.status_code,
        r1.json() if r1.headers.get("content-type", "").startswith("application/json") else r1.text,
        r2.status_code,
        r2.json() if r2.headers.get("content-type", "").startswith("application/json") else r2.text,
    )
    assert codes[1] in {403, 409}
