import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from sk_shared.constants import OrderState
from sk_shared.models.delivery import Shipment, TrackingEvent
from sk_shared.models.order import OrderStatusHistory

from conftest import build_webhook_payload, make_aftership_signature, seed_couriers, seed_user_order


@pytest.mark.asyncio
async def test_register_shipment_creates_record(client, db_session, aftership_mock, internal_header):
    order_row = await seed_user_order(db_session, order_status=OrderState.PURCHASE_CONFIRMED)
    await seed_couriers(db_session)

    response = await client.post(
        "/api/v1/tracking/register",
        headers=internal_header,
        json={"order_id": order_row.id, "tracking_number": "TCS-12345", "courier_code": "TCS"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["aftership_tracking_id"] == "AT-123"
    assert body["status"] == "label_created"

    shipment = await db_session.scalar(select(Shipment).where(Shipment.order_id == order_row.id))
    assert shipment is not None
    assert shipment.status == "label_created"
    aftership_mock.create_tracking.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_tracking_status_returns_events(client, db_session, user_header):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-XYZ", status="in_transit")
    db_session.add(shipment)
    await db_session.flush()

    db_session.add(
        TrackingEvent(
            shipment_id=shipment.id,
            event_code="InTransit",
            event_description="Left origin",
            location_city="Lahore",
            event_time=shipment.created_at,
        )
    )
    db_session.add(
        TrackingEvent(
            shipment_id=shipment.id,
            event_code="OutForDelivery",
            event_description="Out for delivery",
            location_city="Lahore",
            event_time=shipment.updated_at,
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/tracking/{order_row.id}", headers=user_header)
    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 2
    assert body["status"] == "in_transit"
    assert body["events"][0]["event_code"] == "InTransit"


@pytest.mark.asyncio
async def test_get_tracking_status_returns_events_chronological(client, db_session, user_header):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-XYZ", status="in_transit")
    db_session.add(shipment)
    await db_session.flush()

    older = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    newer = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)

    db_session.add(
        TrackingEvent(
            shipment_id=shipment.id,
            event_code="OutForDelivery",
            event_description="Out for delivery",
            location_city="Lahore",
            event_time=newer,
        )
    )
    db_session.add(
        TrackingEvent(
            shipment_id=shipment.id,
            event_code="InTransit",
            event_description="Left origin",
            location_city="Lahore",
            event_time=older,
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/tracking/{order_row.id}", headers=user_header)
    assert response.status_code == 200

    body = response.json()
    assert len(body["events"]) == 2
    assert body["events"][0]["event_code"] == "InTransit"
    assert body["events"][1]["event_code"] == "OutForDelivery"


@pytest.mark.asyncio
async def test_get_tracking_status_404_when_no_shipment(client, user_header):
    response = await client.get("/api/v1/tracking/9999", headers=user_header)
    assert response.status_code == 404
    assert response.json()["detail"] == "SHIPMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_aftership_webhook_happy_path_in_transit(client, db_session):
    order_row = await seed_user_order(db_session, order_status=OrderState.DELIVERY_PENDING)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="label_created")
    db_session.add(shipment)
    await db_session.commit()

    payload = build_webhook_payload(order_row.id, "TCS-123", "InTransit")
    signature = make_aftership_signature(payload)
    response = await client.post(
        "/api/v1/webhooks/aftership",
        headers={"x-aftership-hmac-sha256": signature},
        content=json.dumps(payload),
    )
    assert response.status_code == 200

    await db_session.refresh(shipment)
    assert shipment.status == "in_transit"
    evt = await db_session.scalar(select(TrackingEvent).where(TrackingEvent.shipment_id == shipment.id))
    assert evt is not None
    assert evt.event_code == "InTransit"

    # Verify Order update
    await db_session.refresh(order_row)
    assert order_row.status == OrderState.IN_TRANSIT
    
    # Verify History
    history = await db_session.scalar(
        select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_row.id, OrderStatusHistory.to_status == OrderState.IN_TRANSIT)
    )
    assert history is not None
    assert "delivery tracking (in_transit)" in history.reason


@pytest.mark.asyncio
async def test_aftership_webhook_delivered_updates_shipment(client, db_session):
    order_row = await seed_user_order(db_session, order_status=OrderState.IN_TRANSIT)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    payload = build_webhook_payload(order_row.id, "TCS-123", "Delivered")
    signature = make_aftership_signature(payload)
    response = await client.post(
        "/api/v1/webhooks/aftership",
        headers={"x-aftership-hmac-sha256": signature},
        content=json.dumps(payload),
    )

    assert response.status_code == 200
    await db_session.refresh(shipment)
    assert shipment.status == "delivered"
    assert shipment.actual_delivery is not None

    # Verify Order update
    await db_session.refresh(order_row)
    assert order_row.status == OrderState.DELIVERED

    # Verify History
    history = await db_session.scalar(
        select(OrderStatusHistory).where(OrderStatusHistory.order_id == order_row.id, OrderStatusHistory.to_status == OrderState.DELIVERED)
    )
    assert history is not None
    assert "delivery tracking (delivered)" in history.reason


@pytest.mark.asyncio
async def test_aftership_webhook_returned_publishes_returned_event(client, db_session):
    order_row = await seed_user_order(db_session, order_status=OrderState.IN_TRANSIT)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    payload = build_webhook_payload(order_row.id, "TCS-123", "Returned")
    signature = make_aftership_signature(payload)
    response = await client.post(
        "/api/v1/webhooks/aftership",
        headers={"x-aftership-hmac-sha256": signature},
        content=json.dumps(payload),
    )

    assert response.status_code == 200
    await db_session.refresh(shipment)
    assert shipment.status == "returned"


@pytest.mark.asyncio
async def test_aftership_webhook_rejects_invalid_hmac(client, db_session):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    payload = build_webhook_payload(order_row.id, "TCS-123", "Returned")
    response = await client.post(
        "/api/v1/webhooks/aftership",
        headers={"x-aftership-hmac-sha256": "bad"},
        content=json.dumps(payload),
    )
    assert response.status_code == 403

    await db_session.refresh(shipment)
    assert shipment.status == "in_transit"
    rows = (await db_session.scalars(select(TrackingEvent).where(TrackingEvent.shipment_id == shipment.id))).all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_aftership_webhook_idempotent(client, db_session):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    payload = build_webhook_payload(order_row.id, "TCS-123", "InTransit")
    signature = make_aftership_signature(payload)

    res1 = await client.post(
        "/api/v1/webhooks/aftership",
        headers={"x-aftership-hmac-sha256": signature},
        content=json.dumps(payload),
    )
    assert res1.status_code == 200

    res2 = await client.post(
        "/api/v1/webhooks/aftership",
        headers={"x-aftership-hmac-sha256": signature},
        content=json.dumps(payload),
    )
    assert res2.status_code == 200

    rows = (await db_session.scalars(select(TrackingEvent).where(TrackingEvent.shipment_id == shipment.id))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_admin_tracking_issues_returns_exceptions(client, db_session, admin_header):
    order_1 = await seed_user_order(db_session, user_id=1001)
    order_2 = await seed_user_order(db_session, user_id=1002)

    db_session.add(Shipment(order_id=order_1.id, courier_name="TCS", tracking_number="A", status="delivery_exception"))
    db_session.add(Shipment(order_id=order_2.id, courier_name="TCS", tracking_number="B", status="delivered"))
    await db_session.commit()

    response = await client.get("/api/v1/admin/tracking/issues", headers=admin_header)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["issues"][0]["issue_type"] == "delivery_exception"


@pytest.mark.asyncio
async def test_register_shipment_unknown_courier_returns_422(client, db_session, internal_header):
    order_row = await seed_user_order(db_session, order_status=OrderState.PURCHASE_CONFIRMED)
    response = await client.post(
        "/api/v1/tracking/register",
        headers=internal_header,
        json={"order_id": order_row.id, "tracking_number": "TCS-12345", "courier_code": "UNKNOWN"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_COURIER_CODE"
