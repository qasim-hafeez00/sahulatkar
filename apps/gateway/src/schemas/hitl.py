from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class HitlQueueItemResponse(BaseModel):
    id: int
    uuid: UUID
    order_id: int
    execution_id: int | None
    priority: int
    assigned_to: int | None
    status: str
    failure_reason: str | None
    screenshot_s3: str | None
    resolution: str | None
    claimed_at: datetime | None
    in_progress_at: datetime | None
    resolved_at: datetime | None
    sla_deadline: datetime | None


class HitlListResponse(BaseModel):
    items: list[HitlQueueItemResponse]


class HitlResolveRequest(BaseModel):
    resolution: str = Field(..., min_length=2, max_length=100)


class HitlStatusResponse(BaseModel):
    status: Literal["pending", "claimed", "in_progress", "resolved", "cancelled"]