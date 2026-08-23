from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from sk_shared.models.notification import NotificationPriority, DispatchChannel, DispatchStatus

class NotificationItem(BaseModel):
    id: int
    title: str
    body: str
    category: str
    priority: NotificationPriority
    is_read: bool
    created_at: datetime
    source_event: str
    source_reference: Optional[str] = None

    class Config:
        from_attributes = True

class NotificationInboxResponse(BaseModel):
    items: List[NotificationItem]
    total: int
    page: int
    page_size: int
    unread_count: int

class NotificationPreferenceItem(BaseModel):
    category: str
    category_label: str
    sms_enabled: bool = True
    whatsapp_enabled: bool = True
    push_enabled: bool = True
    email_enabled: bool = True
    is_mandatory: bool = False
    mandatory_reason: Optional[str] = None

class NotificationPreferencesResponse(BaseModel):
    preferences: List[NotificationPreferenceItem]

class PreferenceUpdateItem(BaseModel):
    category: str
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None

class PreferenceUpdateRequest(BaseModel):
    preferences: List[PreferenceUpdateItem]

# ── Internal Schemas ─────────────────────────────────────────────────────────

class InternalNotificationRequest(BaseModel):
    user_id: int
    event_type: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    template_vars: Dict[str, Any] = Field(default_factory=dict)
    channels: Optional[List[DispatchChannel]] = None
    idempotency_key: str
    source_reference: Optional[str] = None

class OTPRequest(BaseModel):
    phone: str
    otp_code: str
    purpose: str # "registration" | "contract_sign" | "payment_auth"
    expires_in_seconds: int = 300
    channels: Optional[List[DispatchChannel]] = None

class BulkNotificationItem(BaseModel):
    user_id: int
    template_vars: Dict[str, Any]
    idempotency_key: str

class BulkNotificationRequest(BaseModel):
    event_type: str
    notifications: List[BulkNotificationItem]

# ── Admin Schemas ────────────────────────────────────────────────────────────

class DispatchInfo(BaseModel):
    channel: DispatchChannel
    status: DispatchStatus
    provider_name: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    attempt_count: int

class AdminNotificationItem(NotificationItem):
    user_phone: Optional[str] = None
    status: str
    channels_requested: List[str]
    dispatches: List[DispatchInfo]

class AdminNotificationListResponse(BaseModel):
    items: List[AdminNotificationItem]
    total: int
    page: int
    page_size: int

class ChannelStats(BaseModel):
    sent: int = 0
    delivered: int = 0
    failed: int = 0
    delivery_rate: float = 0.0

class AdminStatsResponse(BaseModel):
    period: Dict[str, str]
    total_notifications: int
    by_status: Dict[str, int]
    by_channel: Dict[str, ChannelStats]
    by_category: Dict[str, int]
    dlq_depth: int
    avg_dispatch_latency_ms: Dict[str, int]
