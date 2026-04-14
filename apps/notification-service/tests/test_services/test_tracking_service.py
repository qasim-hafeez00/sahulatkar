import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from sk_shared.models.delivery import Shipment, TrackingEvent

from src.services.aftership_client import AfterShipClient
from sk_shared.events import event_channel
from src.services.tracking_service import AFTERSHIP_STATUS_MAP, TrackingService
from conftest import build_webhook_payload, seed_couriers, seed_user_order


@pytest.mark.asyncio
async def test_aftership_status_map_completeness():
    expected = {"InTransit", "OutForDelivery", "Delivered", "AttemptFail", "Exception", "Returned", "InfoReceived", "Pending", "Pickup"}
    assert set(AFTERSHIP_STATUS_MAP.keys()) == expected


@pytest.mark.asyncio
async def test_register_shipment_calls_aftership_and_saves(db_session, redis_mock, aftership_mock):
    order_row = await seed_user_order(db_session)
    await seed_couriers(db_session)
    service = TrackingService(db=db_session, redis=redis_mock, aftership=aftership_mock)

    shipment = await service.register_shipment(order_id=order_row.id, tracking_number="TCS-123", courier_code="TCS")

    assert shipment.id is not None
    assert shipment.aftership_tracking_id == "AT-123"
    aftership_mock.create_tracking.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_webhook_creates_tracking_event(db_session, redis_mock, aftership_mock):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="label_created")
    db_session.add(shipment)
    await db_session.commit()

    service = TrackingService(db=db_session, redis=redis_mock, aftership=aftership_mock)
    payload = build_webhook_payload(order_row.id, "TCS-123", "InTransit")
    await service.process_aftership_webhook(payload)

    rows = (await db_session.scalars(select(TrackingEvent).where(TrackingEvent.shipment_id == shipment.id))).all()
    assert len(rows) == 1
    await db_session.refresh(shipment)
    assert shipment.status == "in_transit"


@pytest.mark.asyncio
async def test_process_webhook_delivered_updates_shipment(db_session, redis_mock, aftership_mock):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    service = TrackingService(db=db_session, redis=redis_mock, aftership=aftership_mock)
    payload = build_webhook_payload(order_row.id, "TCS-123", "Delivered")
    await service.process_aftership_webhook(payload)

    await db_session.refresh(shipment)
    assert shipment.status == "delivered"
    assert shipment.actual_delivery is not None


@pytest.mark.asyncio
async def test_hmac_verification_correct_secret():
    payload = {"msg": {"tracking": {"id": "AT-1", "tag": "Delivered"}}}
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert AfterShipClient.verify_hmac(body, signature, "secret") is True
    assert AfterShipClient.verify_hmac(body, "bad-signature", "secret") is False


@pytest.mark.asyncio
async def test_delivered_webhook_publishes_status_changed_and_confirmed(db_session, redis_mock, aftership_mock):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    publish_mock = AsyncMock()
    redis_mock.publish = publish_mock

    service = TrackingService(db=db_session, redis=redis_mock, aftership=aftership_mock)
    payload = build_webhook_payload(order_row.id, "TCS-123", "Delivered")
    await service.process_aftership_webhook(payload)

    assert publish_mock.await_count == 2
    first_channel, first_payload = publish_mock.await_args_list[0].args
    second_channel, second_payload = publish_mock.await_args_list[1].args

    first_event = json.loads(first_payload)
    second_event = json.loads(second_payload)

    assert first_channel == event_channel("delivery.status_changed")
    assert second_channel == event_channel("delivery.confirmed")
    assert first_event["payload"]["order_id"] == order_row.id
    assert first_event["payload"]["shipment_id"] == shipment.id
    assert first_event["payload"]["previous_status"] == "in_transit"
    assert first_event["payload"]["new_status"] == "delivered"
    assert second_event["payload"]["order_id"] == order_row.id
    assert second_event["payload"]["new_status"] == "delivered"


@pytest.mark.asyncio
async def test_returned_webhook_publishes_status_changed_and_returned(db_session, redis_mock, aftership_mock):
    order_row = await seed_user_order(db_session)
    shipment = Shipment(order_id=order_row.id, courier_name="TCS", tracking_number="TCS-123", status="in_transit")
    db_session.add(shipment)
    await db_session.commit()

    publish_mock = AsyncMock()
    redis_mock.publish = publish_mock

    service = TrackingService(db=db_session, redis=redis_mock, aftership=aftership_mock)
    payload = build_webhook_payload(order_row.id, "TCS-123", "Returned")
    await service.process_aftership_webhook(payload)

    assert publish_mock.await_count == 2
    first_channel, first_payload = publish_mock.await_args_list[0].args
    second_channel, second_payload = publish_mock.await_args_list[1].args

    first_event = json.loads(first_payload)
    second_event = json.loads(second_payload)

    assert first_channel == event_channel("delivery.status_changed")
    assert second_channel == event_channel("delivery.returned")
    assert first_event["payload"]["order_id"] == order_row.id
    assert second_event["payload"]["order_id"] == order_row.id
    assert second_event["payload"]["new_status"] == "returned"


@pytest.mark.asyncio
async def test_register_emits_status_changed_with_transition_fields(db_session, redis_mock, aftership_mock):
    order_row = await seed_user_order(db_session)
    await seed_couriers(db_session)

    publish_mock = AsyncMock()
    redis_mock.publish = publish_mock

    service = TrackingService(db=db_session, redis=redis_mock, aftership=aftership_mock)
    shipment = await service.register_shipment(order_id=order_row.id, tracking_number="TCS-123", courier_code="TCS")

    publish_mock.assert_awaited_once()
    channel, payload = publish_mock.await_args.args
    event_data = json.loads(payload)

    assert channel == event_channel("delivery.status_changed")
    assert event_data["payload"]["order_id"] == order_row.id
    assert event_data["payload"]["shipment_id"] == shipment.id
    assert event_data["payload"]["previous_status"] is None
    assert event_data["payload"]["new_status"] == "label_created"
