import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from sk_shared.models.auth import AdminUser, User
from sk_shared.models.order import Order
from sk_shared.security import create_access_token
from src.config import settings
from src.main import app
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin_with_permissions(role: str, permissions: list[str]) -> str:
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            uuid=uuid.uuid4(),
            email=f"{role}-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="fixture-not-used",
            mfa_enabled=False,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {"admin_id": admin.id, "role": role, "permissions": permissions, "token_type": "admin"},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=3600),
    )
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if hasattr(app.state, "redis") and app.state.redis is not None:
        await app.state.redis.set(f"sk:auth:admin_session:{token_hash}", f"{admin.id}:{role}", 3600)
    return token


async def test_support_cannot_access_financial_data(client, test_user):
    user, _ = test_user
    token = await _seed_admin_with_permissions("support", ["read_user"])

    r = await client.get(f"/api/v1/admin/users/{user.id}/financial-summary", headers=_auth(token))
    assert r.status_code == 403


async def test_analyst_cannot_update_user_status(client, test_user):
    user, _ = test_user
    token = await _seed_admin_with_permissions("analyst", ["read_reports", "read_user"])

    r = await client.put(
        f"/api/v1/admin/users/{user.id}/status",
        json={"status": "suspended"},
        headers=_auth(token),
    )
    assert r.status_code == 403


async def test_kyc_reviewer_cannot_manage_risk(client):
    token = await _seed_admin_with_permissions("kyc_reviewer", ["manage_kyc_queue", "read_user"])

    r = await client.post(
        "/api/v1/admin/risk/blacklist",
        json={"entry_type": "phone", "value": "+923001112233", "reason": "test"},
        headers=_auth(token),
    )
    assert r.status_code == 403


async def test_operations_manager_can_access_hitl(client, test_user, db_session):
    user, _ = test_user
    await db_session.execute(update(User).where(User.id == user.id).values(status="active"))
    await db_session.commit()

    order = Order(user_id=user.id, status="purchase_failed", total_amount=1000, product_description="test")
    db_session.add(order)
    await db_session.commit()

    token = await _seed_admin_with_permissions("operations_manager", ["manage_orders", "read_user"])
    r = await client.get("/api/v1/admin/hitl/queue", headers=_auth(token))
    assert r.status_code == 200
