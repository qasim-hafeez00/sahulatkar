from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.core.http_client import InternalServiceClient

pytestmark = pytest.mark.asyncio

async def test_registration_and_resend_otp(client, monkeypatch):
    mock_send = AsyncMock(return_value=True)
    monkeypatch.setattr(InternalServiceClient, "send_otp", mock_send)
    monkeypatch.setattr(settings, "NOTIFICATION_SMS_ENABLED", True)

    # 1. Initiate
    resp = await client.post("/api/v1/auth/register/initiate", json={
        "phone": "+923000000001",
        "first_name": "Test",
        "last_name": "User"
    })
    assert resp.status_code == 200
    otp_token = resp.json()["otp_token"]

    # 2. Resend
    resp_resend = await client.post("/api/v1/auth/otp/resend", json={
        "otp_token": otp_token
    })
    assert resp_resend.status_code == 200
    new_token = resp_resend.json()["otp_token"]
    assert new_token != otp_token

    # P1-10: both the initial send and the resend must actually dispatch an
    # OTP for delivery via notification-service, not just log/return it.
    assert mock_send.await_count == 2
    for call in mock_send.await_args_list:
        assert call.kwargs["phone"] == "+923000000001"
        assert call.kwargs["purpose"] == "registration"

async def test_login_strikes_lockout(client, test_user):
    user, _ = test_user
    for i in range(5):
        resp = await client.post("/api/v1/auth/login", json={
            "phone": user.phone,
            "password": "wrongpassword"
        })
        assert resp.status_code == 401
    
    # 6th should be locked
    resp_locked = await client.post("/api/v1/auth/login", json={
        "phone": user.phone,
        "password": "wrongpassword"
    })
    assert resp_locked.status_code == 401
    assert resp_locked.json()["detail"] == "Account is temporarily locked"
