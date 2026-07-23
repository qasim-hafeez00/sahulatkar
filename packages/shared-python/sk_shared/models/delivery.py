from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Courier(Base, TimestampMixin):
    __tablename__ = "couriers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    tracking_url_template: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    api_key_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    coverage_provinces: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_cod_available: Mapped[bool] = mapped_column(nullable=False, default=True)
    avg_delivery_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    aftership_slug: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class Shipment(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    courier_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("couriers.id", ondelete="SET NULL"), nullable=True)
    courier_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    aftership_tracking_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="label_created")
    estimated_delivery: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_shipments_order_id", "order_id", unique=True),
        Index("ix_shipments_status_created", "status", "created_at"),
    )


class TrackingEvent(Base, TimestampMixin):
    __tablename__ = "tracking_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shipment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    event_code: Mapped[str] = mapped_column(String(50), nullable=False)
    event_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    courier_raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # NOTE: naive on purpose — event_time is the RANGE partition key on this table
    # and Postgres refuses to ALTER its type, so callers must pass naive UTC
    # datetimes here (e.g. datetime.now(timezone.utc).replace(tzinfo=None)).
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_tracking_events_shipment_id", "shipment_id"),
        Index("ix_tracking_events_event_time", "event_time"),
        Index("ix_tracking_events_shipment_time", "shipment_id", "event_time"),
    )
