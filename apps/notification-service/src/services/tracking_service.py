from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, RedisNS, RedisTTL
from sk_shared.events import (
    EVENT_DELIVERY_CONFIRMED,
    EVENT_DELIVERY_RETURNED,
    EVENT_DELIVERY_STATUS_CHANGED,
    build_event_envelope,
    event_channel,
)
from sk_shared.models.auth import User
from sk_shared.models.delivery import Courier, Shipment, TrackingEvent
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.schemas.tracking import ShipmentStatusResponse, TrackingEventResponse, TrackingIssue
from src.services.aftership_client import AfterShipClient


AFTERSHIP_STATUS_MAP = {
    "InTransit": "in_transit",
    "OutForDelivery": "out_for_delivery",
    "Delivered": "delivered",
    "AttemptFail": "delivery_attempted",
    "Exception": "delivery_exception",
    "Returned": "returned",
    "InfoReceived": "label_created",
    "Pending": "label_created",
    "Pickup": "picked_up",
}


class TrackingService:
    def __init__(self, db: AsyncSession, redis: RedisClient, aftership: AfterShipClient):
        self.db = db
        self.redis = redis
        self.aftership = aftership

    async def register_shipment(self, order_id: int, tracking_number: str, courier_code: str) -> Shipment:
        courier = await self.db.scalar(
            select(Courier).where(Courier.code == courier_code.upper(), Courier.is_active.is_(True))
        )
        if courier is None:
            raise HTTPException(status_code=422, detail="INVALID_COURIER_CODE")

        existing = await self.db.scalar(select(Shipment).where(Shipment.order_id == order_id, Shipment.deleted_at.is_(None)))
        if existing is not None:
            return existing

        tracking = await self.aftership.create_tracking(
            tracking_number=tracking_number,
            slug=courier.aftership_slug or courier.code.lower(),
            order_id=order_id,
        )

        shipment = Shipment(
            order_id=order_id,
            courier_id=courier.id,
            courier_name=courier.name,
            tracking_number=tracking_number,
            aftership_tracking_id=str(tracking.get("id")) if tracking.get("id") else None,
            status="label_created",
        )
        self.db.add(shipment)
        await self.db.commit()
        await self.db.refresh(shipment)

        await self._publish_delivery_event(
            event=EVENT_DELIVERY_STATUS_CHANGED,
            order_id=order_id,
            extra={
                "shipment_id": shipment.id,
                "previous_status": None,
                "new_status": shipment.status,
                "tracking_number": shipment.tracking_number,
            },
        )
        await self._cache_shipment(shipment)
        return shipment

    async def process_aftership_webhook(self, payload: dict[str, Any]) -> None:
        tracking = self._extract_tracking(payload)
        if tracking is None:
            raise HTTPException(status_code=422, detail="INVALID_WEBHOOK_PAYLOAD")

        tag = str(tracking.get("tag") or "Pending")
        mapped_status = AFTERSHIP_STATUS_MAP.get(tag, "delivery_exception")
        tracking_number = tracking.get("tracking_number")
        tracking_id = tracking.get("id")
        order_id = self._safe_int(tracking.get("order_id"))

        shipment = await self._find_shipment(
            order_id=order_id,
            tracking_number=tracking_number,
            aftership_tracking_id=str(tracking_id) if tracking_id else None,
        )
        if shipment is None:
            if order_id is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SHIPMENT_NOT_FOUND")

            shipment = Shipment(
                order_id=order_id,
                courier_name=tracking.get("slug"),
                tracking_number=tracking_number,
                aftership_tracking_id=str(tracking_id) if tracking_id else None,
                status="label_created",
            )
            self.db.add(shipment)
            await self.db.flush()

        previous_status = shipment.status
        checkpoints = tracking.get("checkpoints") or []
        if checkpoints:
            for checkpoint in checkpoints:
                event_time = self._parse_datetime(
                    checkpoint.get("checkpoint_time")
                    or checkpoint.get("created_at")
                    or checkpoint.get("time")
                )
                event_code = str(checkpoint.get("tag") or tag)

                exists = await self.db.scalar(
                    select(TrackingEvent).where(
                        TrackingEvent.shipment_id == shipment.id,
                        TrackingEvent.event_code == event_code,
                        TrackingEvent.event_time == event_time,
                    )
                )
                if exists is not None:
                    continue

                self.db.add(
                    TrackingEvent(
                        shipment_id=shipment.id,
                        event_code=event_code,
                        event_description=checkpoint.get("message") or checkpoint.get("tag") or tag,
                        location_city=checkpoint.get("city") or checkpoint.get("location"),
                        courier_raw_data=checkpoint,
                        event_time=event_time,
                    )
                )

        shipment.status = mapped_status
        if mapped_status == "delivered":
            shipment.actual_delivery = self._parse_datetime(tracking.get("delivered_at"))

        await self.db.commit()
        await self.db.refresh(shipment)

        status_payload = {
            "shipment_id": shipment.id,
            "previous_status": previous_status,
            "new_status": shipment.status,
            "tracking_number": shipment.tracking_number,
            "aftership_tracking_id": shipment.aftership_tracking_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }

        await self._publish_delivery_event(
            event=EVENT_DELIVERY_STATUS_CHANGED,
            order_id=shipment.order_id,
            extra=status_payload,
        )

        if mapped_status == "delivered":
            await self._publish_delivery_event(
                event=EVENT_DELIVERY_CONFIRMED,
                order_id=shipment.order_id,
                extra=status_payload,
            )

        if mapped_status == "returned":
            await self._publish_delivery_event(
                event=EVENT_DELIVERY_RETURNED,
                order_id=shipment.order_id,
                extra=status_payload,
            )

        # Update associated Order state if it's a critical transition
        order_mapped_status = None
        if shipment.status == "in_transit":
            order_mapped_status = OrderState.IN_TRANSIT
        elif shipment.status == "delivered":
            order_mapped_status = OrderState.DELIVERED
        elif shipment.status == "returned":
            order_mapped_status = OrderState.RETURNED

        if order_mapped_status:
            order = await self.db.get(Order, shipment.order_id)
            if order and order.status != order_mapped_status:
                self.db.add(
                    OrderStatusHistory(
                        order_id=order.id,
                        from_status=order.status,
                        to_status=order_mapped_status,
                        reason=f"Auto-updated via delivery tracking ({shipment.status})",
                    )
                )
                order.status = order_mapped_status
                await self.db.commit()

        await self._cache_shipment(shipment)

    async def get_shipment_status(self, order_id: int) -> ShipmentStatusResponse:
        shipment = await self.db.scalar(select(Shipment).where(Shipment.order_id == order_id, Shipment.deleted_at.is_(None)))
        if shipment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SHIPMENT_NOT_FOUND")

        rows = await self.db.scalars(
            select(TrackingEvent)
            .where(TrackingEvent.shipment_id == shipment.id)
            .order_by(TrackingEvent.event_time.asc())
        )
        events = [
            TrackingEventResponse(
                time=e.event_time,
                description=e.event_description or e.event_code,
                location=e.location_city,
                event_code=e.event_code,
            )
            for e in rows.all()
        ]

        return ShipmentStatusResponse(
            order_id=shipment.order_id,
            courier=shipment.courier_name or "unknown",
            tracking_number=shipment.tracking_number,
            aftership_tracking_id=shipment.aftership_tracking_id,
            status=shipment.status,
            estimated_delivery=shipment.estimated_delivery,
            actual_delivery=shipment.actual_delivery,
            events=events,
        )

    async def get_admin_issues(self) -> list[TrackingIssue]:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await self.db.execute(
            select(Shipment, Order, User)
            .join(Order, Order.id == Shipment.order_id)
            .join(User, User.id == Order.user_id)
            .where(
                Shipment.deleted_at.is_(None),
                or_(
                    Shipment.status.in_(["delivery_attempted", "delivery_exception", "returned"]),
                    and_(Shipment.status == "in_transit", Shipment.updated_at < stale_cutoff),
                ),
            )
            .order_by(Shipment.updated_at.asc())
        )

        now = datetime.now(timezone.utc)
        issues: list[TrackingIssue] = []
        for shipment, _order, user in result.all():
            days = (now - shipment.updated_at.replace(tzinfo=timezone.utc)).days if shipment.updated_at else 0
            issues.append(
                TrackingIssue(
                    order_id=shipment.order_id,
                    customer_name=user.phone,
                    courier=shipment.courier_name or "unknown",
                    tracking_number=shipment.tracking_number,
                    issue_type=shipment.status,
                    days_in_state=max(days, 0),
                )
            )
        return issues

    async def _publish_delivery_event(self, event: str, order_id: int, extra: dict[str, Any]) -> None:
        envelope = build_event_envelope(
            event=event,
            source_service=settings.SERVICE_NAME,
            correlation_id=f"order-{order_id}",
            payload={"order_id": order_id, **extra},
        )
        await self.redis.publish(event_channel(event), envelope.to_json())

    async def _cache_shipment(self, shipment: Shipment) -> None:
        await self.redis.set_json(
            f"{RedisNS.SHIPMENT_TRACKING}:{shipment.order_id}",
            {
                "order_id": shipment.order_id,
                "shipment_id": shipment.id,
                "status": shipment.status,
                "tracking_number": shipment.tracking_number,
                "aftership_tracking_id": shipment.aftership_tracking_id,
            },
            ttl=RedisTTL.PRODUCT_CACHE,
        )

    async def _find_shipment(
        self,
        *,
        order_id: Optional[int],
        tracking_number: Optional[str],
        aftership_tracking_id: Optional[str],
    ) -> Shipment | None:
        where_clauses = [Shipment.deleted_at.is_(None)]

        dynamic_clauses = []
        if order_id is not None:
            dynamic_clauses.append(Shipment.order_id == order_id)
        if tracking_number:
            dynamic_clauses.append(Shipment.tracking_number == tracking_number)
        if aftership_tracking_id:
            dynamic_clauses.append(Shipment.aftership_tracking_id == aftership_tracking_id)

        if not dynamic_clauses:
            return None

        where_clauses.append(or_(*dynamic_clauses))
        return await self.db.scalar(select(Shipment).where(*where_clauses))

    @staticmethod
    def _extract_tracking(payload: dict[str, Any]) -> dict[str, Any] | None:
        msg = payload.get("msg") or {}
        if isinstance(msg, dict):
            if isinstance(msg.get("tracking"), dict):
                return msg["tracking"]
            if isinstance(msg.get("trackings"), list) and msg["trackings"]:
                first = msg["trackings"][0]
                if isinstance(first, dict):
                    return first
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            candidate = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(candidate)
                if parsed.tzinfo is None:
                    return parsed
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pass
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def dedup_hash(payload: dict[str, Any]) -> str:
        tracking = TrackingService._extract_tracking(payload) or {}
        tracking_id = str(tracking.get("id") or tracking.get("tracking_number") or "")
        tag = str(tracking.get("tag") or "")
        checkpoints = tracking.get("checkpoints") or []
        checkpoint_time = ""
        if checkpoints:
            last = checkpoints[-1]
            checkpoint_time = str(last.get("checkpoint_time") or last.get("created_at") or "")
        raw = f"{tracking_id}:{tag}:{checkpoint_time}"
        return sha256(raw.encode("utf-8")).hexdigest()
