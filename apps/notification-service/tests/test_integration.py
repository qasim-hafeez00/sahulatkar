import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings

@pytest.mark.asyncio
async def test_otp_multi_channel_integration(client: AsyncClient, db_session: AsyncSession, internal_header: dict):
    # Test sending OTP via multiple channels
    payload = {
        "phone": "+923001234567",
        "otp_code": "123456",
        "purpose": "registration",
        "expires_in_seconds": 300,
        "channels": ["sms", "whatsapp"]
    }
    
    # Correct path: /api/v1/internal/notifications/otp
    resp = await client.post("/api/v1/internal/notifications/otp", json=payload, headers=internal_header)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    
    # Verify both dispatches exist
    from sk_shared.models.notification import NotificationDispatch
    from sqlalchemy import select
    dispatches = (await db_session.scalars(select(NotificationDispatch).where(NotificationDispatch.notification_id == data["notification_id"]))).all()
    assert len(dispatches) == 2
    channels = [d.channel for d in dispatches]
    assert "sms" in channels
    assert "whatsapp" in channels

@pytest.mark.asyncio
async def test_otp_rate_limiting_daily(client: AsyncClient, internal_header: dict):
    phone = "+923009999999"
    payload = {
        "phone": phone,
        "otp_code": "111111",
        "purpose": "registration"
    }
    
    # Fill hourly limit (default is 5)
    for _ in range(settings.OTP_SMS_RATE_LIMIT_PER_PHONE_PER_HOUR):
        await client.post("/api/v1/internal/notifications/otp", json=payload, headers=internal_header)
        
    resp = await client.post("/api/v1/internal/notifications/otp", json=payload, headers=internal_header)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "TOO_MANY_OTP_REQUESTS"

@pytest.mark.asyncio
async def test_global_unsubscribe_enforcement(client: AsyncClient, db_session: AsyncSession, internal_header: dict, user_header: dict):
    user_id = 42
    
    # 1. Subscribe globally first (default)
    # 2. Send a non-compliance notification
    payload = {
        "user_id": user_id,
        "event_type": "kyc.approved",
        "template_vars": {"credit_limit": "5000"},
        "idempotency_key": "integration-unsub-1"
    }
    resp = await client.post("/api/v1/internal/notifications/send", json=payload, headers=internal_header)
    assert resp.status_code == 200
    
    # 3. Global Unsubscribe
    resp = await client.post("/api/v1/notifications/unsubscribe", headers=user_header)
    assert resp.status_code == 200
    
    # 4. Try sending again (new idempotency key)
    payload["idempotency_key"] = "integration-unsub-2"
    resp = await client.post("/api/v1/internal/notifications/send", json=payload, headers=internal_header)
    assert resp.status_code == 200
    notif_id = resp.json()["notification_id"]
    
    # 5. Verify no dispatches were created for the second notification
    from sk_shared.models.notification import NotificationDispatch
    from sqlalchemy import select
    dispatches = (await db_session.scalars(select(NotificationDispatch).where(NotificationDispatch.notification_id == notif_id))).all()
    assert len(dispatches) == 0

@pytest.mark.asyncio
async def test_shariah_guard_late_fee(client: AsyncClient, db_session: AsyncSession, internal_header: dict):
    settings.CHARITY_ORGANIZATION_NAME = "Edhi Foundation"
    
    payload = {
        "user_id": 42,
        "event_type": "billing.late_fee_applied",
        "template_vars": {"fee_amount": "500", "days_overdue": "5", "order_id": "123"},
        "idempotency_key": "shariah-guard-test"
    }
    
    resp = await client.post("/api/v1/internal/notifications/send", json=payload, headers=internal_header)
    assert resp.status_code == 200
    resp.json()["notification_id"]
    
    from src.services.template_service import TemplateService
    ts = TemplateService()
    _, body = ts.render("billing.late_fee_applied", "sms", payload["template_vars"])
    
    assert "Edhi Foundation" in body
    assert "100% of this amount is donated to" in body
