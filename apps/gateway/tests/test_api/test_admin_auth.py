import asyncio
import pytest
import hashlib
import pyotp
from httpx import AsyncClient
from sqlalchemy import select
from sk_shared.redis_client import RedisClient
from sk_shared.security import get_password_hash
from sk_shared.models.auth import AdminUser, AdminSession
from src.core.kms import KMSProvider
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


async def test_admin_login_persists_and_enforces_single_session(client: AsyncClient, db_session, redis_mock: RedisClient):
    """Bug 1 regression: admin_login must actually write to the admin_sessions
    table (not just Redis) via the AdminSession ORM model, and logging in a
    second time must revoke the first session row — proving the
    single-session-per-admin policy is genuinely enforced end-to-end, not
    silently skipped because the table didn't exist."""
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            email="dualsession@test.com",
            password_hash=get_password_hash("ValidPass123"),
            mfa_enabled=False,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id

    payload = {"email": "dualsession@test.com", "password": "ValidPass123"}

    # First login
    resp1 = await client.post("/api/v1/admin/auth/login", json=payload)
    assert resp1.status_code == 200
    token_hash_1 = hashlib.sha256(resp1.json()["access_token"].encode()).hexdigest()

    async with TestingSessionLocal() as session:
        rows = (
            await session.execute(select(AdminSession).where(AdminSession.admin_user_id == admin_id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].token_hash == token_hash_1
        assert rows[0].revoked_at is None

    # Second login — must revoke the first session row and create a new one.
    resp2 = await client.post("/api/v1/admin/auth/login", json=payload)
    assert resp2.status_code == 200
    token_hash_2 = hashlib.sha256(resp2.json()["access_token"].encode()).hexdigest()
    assert token_hash_2 != token_hash_1

    async with TestingSessionLocal() as session:
        rows = (
            await session.execute(
                select(AdminSession).where(AdminSession.admin_user_id == admin_id).order_by(AdminSession.id)
            )
        ).scalars().all()
        assert len(rows) == 2
        first, second = rows
        assert first.token_hash == token_hash_1
        assert first.revoked_at is not None
        assert second.token_hash == token_hash_2
        assert second.revoked_at is None

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


async def test_admin_totp_lockout_after_failed_attempts(client: AsyncClient):
    secret = pyotp.random_base32()
    encrypted_secret = KMSProvider().encrypt(secret)

    async with TestingSessionLocal() as session:
        admin = AdminUser(
            email="totp-lock@test.com",
            password_hash=get_password_hash("ValidPass123"),
            mfa_enabled=True,
            mfa_secret_encrypted=encrypted_secret,
        )
        session.add(admin)
        await session.commit()

    payload = {
        "email": "totp-lock@test.com",
        "password": "ValidPass123",
        "totp_code": "000000",
    }

    for _ in range(5):
        response = await client.post("/api/v1/admin/auth/login", json=payload)
        assert response.status_code == 401

    locked = await client.post("/api/v1/admin/auth/login", json=payload)
    assert locked.status_code == 429
    assert locked.json()["detail"] == "TOTP_LOCKED_TOO_MANY_ATTEMPTS"


async def test_create_admin_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    payload = {
        "email": "newadmin@test.com",
        "password": "StrongPass123",
        "role": "analyst",
    }
    response = await client.post("/api/v1/admin/auth/admins", json=payload, headers=_auth(admin_token))
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newadmin@test.com"
    assert "admin_id" in data


async def test_list_admin_roles_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/auth/roles", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "roles" in data
    assert any(role["name"] == "super_admin" for role in data["roles"])
