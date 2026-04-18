import pytest
from sqlalchemy import select
from sk_shared.models.auth import User
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio

async def test_registration_and_resend_otp(client):
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
