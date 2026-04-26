import pytest
import hashlib
import hmac
import json
import httpx
import respx
from unittest.mock import patch, MagicMock, AsyncMock
from src.config import settings

@pytest.mark.asyncio
async def test_otp_rate_limiting(client, redis_mock, internal_header):
    # Set a low limit for testing
    settings.OTP_SMS_RATE_LIMIT_PER_PHONE_PER_HOUR = 2
    phone = "+923001234567"
    
    payload = {
        "phone": phone,
        "otp_code": "123456",
        "purpose": "registration"
    }
    
    # First request
    resp = await client.post("/api/v1/internal/notifications/otp", json=payload, headers=internal_header)
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    
    # Second request
    resp = await client.post("/api/v1/internal/notifications/otp", json=payload, headers=internal_header)
    assert resp.status_code == 200
    
    # Third request (should be rate limited)
    resp = await client.post("/api/v1/internal/notifications/otp", json=payload, headers=internal_header)
    assert resp.status_code == 429
    assert resp.json()["detail"] == "TOO_MANY_OTP_REQUESTS"

@pytest.mark.asyncio
async def test_jazz_sms_webhook_verification(client):
    settings.JAZZ_SMS_WEBHOOK_SECRET = "jazz-secret"
    payload = {"message_id": "M123", "status": "delivered"}
    body = json.dumps(payload).encode("utf-8")
    
    # Valid signature
    signature = hmac.new(b"jazz-secret", body, hashlib.sha256).hexdigest()
    resp = await client.post(
        "/api/v1/webhooks/sms-delivery", 
        content=body, 
        headers={"x-jazz-hmac-sha256": signature}
    )
    assert resp.status_code == 200
    
    # Invalid signature
    resp = await client.post(
        "/api/v1/webhooks/sms-delivery", 
        content=body, 
        headers={"x-jazz-hmac-sha256": "wrong"}
    )
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_sendgrid_unsubscribe_category_specific(client, db_session):
    from sk_shared.models.notification import Notification, NotificationDispatch, NotificationPreference
    from sk_shared.models.auth import User
    
    # Setup: User with preferences
    user = User(phone="+923000000042")
    db_session.add(user)
    await db_session.flush()
    
    pref_billing = NotificationPreference(user_id=user.id, category="billing", email_enabled=True)
    pref_order = NotificationPreference(user_id=user.id, category="order", email_enabled=True)
    db_session.add_all([pref_billing, pref_order])
    
    # Setup: Notification for billing
    notif = Notification(
        user_id=user.id, source_event="billing.payment_due", category="billing",
        title="Due", body="Pay", idempotency_key="k1", channels_requested=["email"]
    )
    db_session.add(notif)
    await db_session.flush()
    
    dispatch = NotificationDispatch(
        notification_id=notif.id, channel="email", status="sent", provider_message_id="SG123"
    )
    db_session.add(dispatch)
    await db_session.commit()
    
    # Webhook: Unsubscribe for this message
    payload = [{"event": "unsubscribe", "sg_message_id": "SG123.abc.def"}]
    resp = await client.post("/api/v1/webhooks/sendgrid", json=payload)
    assert resp.status_code == 200
    
    # Verify: Billing email disabled, but Order email still enabled
    await db_session.refresh(pref_billing)
    await db_session.refresh(pref_order)
    assert pref_billing.email_enabled is False
    assert pref_order.email_enabled is True

@pytest.mark.asyncio
async def test_shariah_compliance_guard(client, db_session, admin_header):
    from sk_shared.models.notification import NotificationTemplate
    
    # Setup: Compliance template
    tmpl = NotificationTemplate(
        event_type="billing.late_fee_applied", channel="sms", body_template="Old", is_active=True
    )
    db_session.add(tmpl)
    await db_session.commit()
    
    # Update template
    headers = {**admin_header, "x-admin-permissions": "admin:notifications:write"}
    resp = await client.put(
        f"/api/v1/admin/notifications/templates/{tmpl.id}", 
        json={"body_template": "New Body"}, 
        headers=headers
    )
    assert resp.status_code == 200
    
    # Verify: Automatically deactivated
    await db_session.refresh(tmpl)
    assert tmpl.body_template == "New Body"
    assert tmpl.is_active is False

@pytest.mark.asyncio
async def test_enhanced_health_check(client, redis_mock):
    from src.core.event_listeners import listener_state
    from src.services.notification_service import DISPATCHERS
    
    listener_state["running"] = True
    
    # Mock all dispatchers to be healthy
    for dispatcher in DISPATCHERS.values():
        dispatcher.health_check = AsyncMock(return_value=True)

    # Setup some queue data
    await redis_mock.lpush(settings.NOTIFICATION_QUEUE_KEY, "1")
    await redis_mock.lpush(settings.NOTIFICATION_QUEUE_KEY, "2")
    
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    
    assert "queues" in data
    assert data["queues"]["main"] >= 2
    assert "dispatchers" in data
    assert "sms" in data["dispatchers"]

@pytest.mark.asyncio
async def test_jazz_sms_failover(client):
    from src.config import settings
    
    settings.SMS_FALLBACK_PROVIDER = "twilio"
    settings.TWILIO_AUTH_TOKEN = "test-token"
    settings.TWILIO_ACCOUNT_SID = "test-sid"
    
    # Re-initialize the dispatcher so it picks up the new settings
    from src.services.notification_service import DISPATCHERS
    from src.dispatchers.sms_dispatcher import TwilioSMSDispatcher
    DISPATCHERS["sms"]._fallback = TwilioSMSDispatcher()

    
    # Mock responses for both Jazz and Twilio
    jazz_url = settings.JAZZ_SMS_API_URL
    twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"

    # We use respx for mocking external calls
    with respx.mock:
        # Pass through the test client requests
        respx.route(host="test").pass_through()
        
        respx.post(jazz_url).mock(return_value=httpx.Response(500))
        respx.post(twilio_url).mock(return_value=httpx.Response(201, json={"sid": "TW123"}))
        
        payload = {
            "phone": "+923001234567",
            "otp_code": "123456",
            "purpose": "registration"
        }
        from src.config import settings as cfg
        header = {"x-internal-key": cfg.INTERNAL_API_KEY}
        
        resp = await client.post("/api/v1/internal/notifications/otp", json=payload, headers=header)
        assert resp.status_code == 200
        
        # Verify both were called
        # respx provides calls history
        assert len(respx.calls) >= 2
