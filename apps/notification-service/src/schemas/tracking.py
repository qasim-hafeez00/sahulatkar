from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RegisterTrackingRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    tracking_number: str = Field(..., min_length=3, max_length=100)
    courier_code: str = Field(..., min_length=2, max_length=20)


class RegisterTrackingResponse(BaseModel):
    shipment_id: int
    aftership_tracking_id: Optional[str] = None
    status: str


class TrackingEventResponse(BaseModel):
    time: datetime
    description: str
    location: Optional[str] = None
    event_code: str


class ShipmentStatusResponse(BaseModel):
    order_id: int
    courier: str
    tracking_number: Optional[str] = None
    aftership_tracking_id: Optional[str] = None
    status: str
    estimated_delivery: Optional[date] = None
    actual_delivery: Optional[datetime] = None
    events: list[TrackingEventResponse]


class AfterShipWebhookPayload(BaseModel):
    msg: dict[str, Any]


class WebhookAck(BaseModel):
    received: bool


class TrackingIssue(BaseModel):
    order_id: int
    customer_name: str
    courier: str
    tracking_number: Optional[str]
    issue_type: str
    days_in_state: int


class AdminTrackingIssuesResponse(BaseModel):
    issues: list[TrackingIssue]
    total: int
