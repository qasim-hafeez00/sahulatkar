from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NotificationItem(BaseModel):
    id: int
    category: str
    priority: str
    title: str
    body: str
    is_read: bool
    source_reference: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    unread_count: int
    total: int
