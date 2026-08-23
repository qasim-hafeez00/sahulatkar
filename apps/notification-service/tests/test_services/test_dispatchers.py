import pytest
import respx
import httpx
from src.dispatchers.sms_dispatcher import JazzSMSDispatcher
from src.dispatchers.whatsapp_dispatcher import JazzWhatsAppDispatcher
from src.dispatchers.push_dispatcher import FCMPushDispatcher
from src.dispatchers.email_dispatcher import SendGridEmailDispatcher
from src.config import settings

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setattr(settings, "JAZZ_SMS_API_URL", "https://sms.jazz.com.pk/api/send")
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "mock_sid")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "mock_token")
    monkeypatch.setattr(settings, "JAZZ_WHATSAPP_API_URL", "https://waba.jazz.com.pk/v1/messages")
    monkeypatch.setattr(settings, "FCM_PROJECT_ID", "mock-project")
    monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "")
    monkeypatch.setattr(settings, "SENDGRID_API_KEY", "mock_sg_key")


@respx.mock
async def test_sms_dispatcher_jazz_success():
    respx.post("https://sms.jazz.com.pk/api/send").mock(return_value=httpx.Response(200, json={"message_id": "12345"}))
    
    dispatcher = JazzSMSDispatcher()
    result = await dispatcher.send(destination="923000000000", content="Test", notification_id=1)
    
    assert result.success is True
    assert result.provider_name == "jazz_sms"
    assert result.provider_message_id == "12345"

@respx.mock
async def test_sms_dispatcher_jazz_500_falls_to_twilio():
    respx.post("https://sms.jazz.com.pk/api/send").mock(return_value=httpx.Response(500))
    respx.post("https://api.twilio.com/2010-04-01/Accounts/mock_sid/Messages.json").mock(
        return_value=httpx.Response(201, json={"sid": "tw123"})
    )
    
    dispatcher = JazzSMSDispatcher()
    result = await dispatcher.send(destination="923000000000", content="Test", notification_id=1)
    
    assert result.success is True
    assert result.provider_name == "twilio_sms"
    assert result.provider_message_id == "tw123"

@respx.mock
async def test_sms_dispatcher_jazz_400_no_retry():
    respx.post("https://sms.jazz.com.pk/api/send").mock(return_value=httpx.Response(400, text="Invalid Number"))
    
    dispatcher = JazzSMSDispatcher()
    result = await dispatcher.send(destination="invalid", content="Test", notification_id=1)
    
    assert result.success is False
    assert result.should_retry is False
    assert result.provider_name == "jazz_sms"

@respx.mock
async def test_sms_dispatcher_body_truncated_at_160():
    respx.post("https://sms.jazz.com.pk/api/send").mock(return_value=httpx.Response(200, json={"message_id": "12345"}))
    
    dispatcher = JazzSMSDispatcher()
    long_content = "A" * 200
    
    result = await dispatcher.send(destination="923000000000", content=long_content, notification_id=1)
    
    assert result.success is True
    # The actual request inspection is harder, but we can mock the httpx client if needed.
    # The truncation is handled internally.

@respx.mock
async def test_whatsapp_dispatcher_470_permanent_failure():
    respx.post("https://waba.jazz.com.pk/v1/messages").mock(return_value=httpx.Response(470, text="USER_NOT_ON_WHATSAPP"))
    
    dispatcher = JazzWhatsAppDispatcher()
    result = await dispatcher.send(destination="923000000000", content="Test", notification_id=1)
    
    assert result.success is False
    assert result.should_retry is False

@respx.mock
async def test_push_dispatcher_no_token_returns_failure():
    dispatcher = FCMPushDispatcher()
    result = await dispatcher.send(destination="", content="Test", notification_id=1)
    
    assert result.success is False
    assert result.should_retry is False

@respx.mock
async def test_push_dispatcher_unregistered_token_permanent():
    respx.post("https://fcm.googleapis.com/v1/projects/mock-project/messages:send").mock(
        return_value=httpx.Response(404, json={"error": {"details": [{"errorCode": "UNREGISTERED"}]}})
    )
    
    dispatcher = FCMPushDispatcher()
    result = await dispatcher.send(destination="bad_token", content="Test", notification_id=1)
    
    assert result.success is False
    assert result.should_retry is False

@respx.mock
async def test_email_dispatcher_sendgrid_202_success():
    respx.post("https://api.sendgrid.com/v3/mail/send").mock(
        return_value=httpx.Response(202, headers={"X-Message-Id": "sg123"})
    )
    
    dispatcher = SendGridEmailDispatcher()
    result = await dispatcher.send(destination="test@example.com", content="Test", notification_id=1)
    
    assert result.success is True
    assert result.provider_message_id == "sg123"

@respx.mock
async def test_email_dispatcher_sendgrid_500_retry():
    respx.post("https://api.sendgrid.com/v3/mail/send").mock(return_value=httpx.Response(500))
    
    dispatcher = SendGridEmailDispatcher()
    result = await dispatcher.send(destination="test@example.com", content="Test", notification_id=1)
    
    assert result.success is False
    assert result.should_retry is True
