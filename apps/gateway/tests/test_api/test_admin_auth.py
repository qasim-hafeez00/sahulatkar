import pytest
import hashlib
from httpx import AsyncClient
from sk_shared.redis_client import RedisClient
from sk_shared.security import get_password_hash
from sk_shared.models.auth import AdminUser
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_admin_login_success(client: AsyncClient, db_session, redis_mock: RedisClient):
    # 1. Seed admin
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            email="login@test.com",
            password_hash=get_password_hash("ValidPass123"),
            mfa_enabled=False
        )
        session.add(admin)
        await session.commit()
    
    # 2. Login
    payload = {"email": "login@test.com", "password": "ValidPass123"}
    response = await client.post("/api/v1/admin/auth/login", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    
    # 3. Verify session in Redis
    token_hash = hashlib.sha256(data["access_token"].encode()).hexdigest()
    session_data = await redis_mock.get(f"sk:auth:admin_session:{token_hash}")
    assert session_data is not None

async def test_admin_login_invalid_password(client: AsyncClient, db_session):
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            email="fail@test.com",
            password_hash=get_password_hash("CorrectPass"),
            mfa_enabled=False
        )
        session.add(admin)
        await session.commit()
        
    payload = {"email": "fail@test.com", "password": "WrongPass"}
    response = await client.post("/api/v1/admin/auth/login", json=payload)
    assert response.status_code == 401

async def test_admin_me_endpoint(client: AsyncClient, test_admin):
    admin, token = test_admin
    response = await client.get("/api/v1/admin/auth/me", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == admin.email
    assert data["mfa_enabled"] is False
    assert "all_actions" in data["permissions"]

async def test_assign_role_invalidates_sessions(client: AsyncClient, test_admin, redis_mock):
    admin, token = test_admin
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Verify session exists
    assert await redis_mock.get(f"sk:auth:admin_session:{token_hash}") is not None
    
    # Assign new role
    payload = {"role": "analyst"}
    response = await client.put(
        f"/api/v1/admin/auth/admins/{admin.id}/role",
        json=payload,
        headers=_auth(token)
    )
    assert response.status_code == 200
    
    # Verify session is GONE (invalidation logic)
    assert await redis_mock.get(f"sk:auth:admin_session:{token_hash}") is None
