import pytest
import uuid
import hashlib
from datetime import timedelta

from sk_shared.constants import OrderState
from sk_shared.models.auth import AdminUser
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from sk_shared.models.product import Merchant, Product
from sk_shared.security import create_access_token
from tests.conftest import TestingSessionLocal
from src.config import settings


pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_order(user_id: int) -> Order:
    async with TestingSessionLocal() as session:
        merchant = Merchant(name="HITL Merchant", normalized_name="hitl-merchant", domain="hitl.example.com")
        session.add(merchant)
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            name="HITL Product",
            url="https://hitl.example.com/p/1",
            currency="PKR",
            cost_price=10000,
            sale_price=10400,
            in_stock=True,
        )
        session.add(product)
        await session.flush()

        order = Order(
            user_id=user_id,
            product_id=product.id,
            status=OrderState.PURCHASE_FAILED,
            total_amount=10400,
            down_payment_amount=2600,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def _seed_hitl(order_id: int, *, status: str = "pending", assigned_to: int | None = None) -> HitlQueue:
    async with TestingSessionLocal() as session:
        item = HitlQueue(
            order_id=order_id,
            execution_id=None,
            priority=2,
            assigned_to=assigned_to,
            status=status,
            failure_reason="checkout_changed",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def _seed_admin_with_token() -> tuple[AdminUser, str]:
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            uuid=uuid.uuid4(),
            email=f"hitl-admin-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="test-hash",
            mfa_enabled=False,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {"admin_id": admin.id, "role": "super_admin", "permissions": ["all_actions"], "token_type": "admin"},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=3600),
    )
    from src.main import app
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session_key = f"sk:auth:admin_session:{token_hash}"
    session_value = f"{admin.id}:super_admin"
    # Write into app.state.redis which is the shared redis_mock injected by override_dependencies
    if hasattr(app.state, "redis") and app.state.redis is not None:
        await app.state.redis.set(session_key, session_value, 3600)
    return admin, token


async def test_hitl_requires_auth(client):
    response = await client.get("/api/v1/admin/hitl/queue")
    assert response.status_code in {401, 403}


async def test_hitl_happy_path_claim_start_resolve(client, test_user):
    user, _ = test_user
    admin, admin_token = await _seed_admin_with_token()

    order = await _seed_order(user.id)
    item = await _seed_hitl(order.id)

    listed = await client.get("/api/v1/admin/hitl/queue", headers=_auth(admin_token))
    assert listed.status_code == 200
    assert any(entry["id"] == item.id for entry in listed.json()["items"])

    claimed = await client.post(f"/api/v1/admin/hitl/{item.id}/claim", headers=_auth(admin_token))
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "claimed"
    assert claimed.json()["assigned_to"] == admin.id

    started = await client.post(f"/api/v1/admin/hitl/{item.id}/start", headers=_auth(admin_token))
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    resolved = await client.post(
        f"/api/v1/admin/hitl/{item.id}/resolve",
        headers=_auth(admin_token),
        json={"resolution": "manual_checkout_completed"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


async def test_hitl_cancel_path(client, test_user):
    user, _ = test_user
    _, admin_token = await _seed_admin_with_token()

    order = await _seed_order(user.id)
    item = await _seed_hitl(order.id, status="pending")

    cancelled = await client.post(f"/api/v1/admin/hitl/{item.id}/cancel", headers=_auth(admin_token))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


async def test_hitl_claim_non_pending_returns_422(client, test_user):
    user, _ = test_user
    admin, admin_token = await _seed_admin_with_token()

    order = await _seed_order(user.id)
    item = await _seed_hitl(order.id, status="claimed", assigned_to=admin.id)

    response = await client.post(f"/api/v1/admin/hitl/{item.id}/claim", headers=_auth(admin_token))
    assert response.status_code == 422
    assert response.json()["detail"] == "HITL_ITEM_NOT_PENDING"


async def test_hitl_queue_detail_returns_item(client, test_user):
    user, _ = test_user
    _, admin_token = await _seed_admin_with_token()

    order = await _seed_order(user.id)
    item = await _seed_hitl(order.id, status="pending")

    response = await client.get(f"/api/v1/admin/hitl/queue/{item.id}", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == item.id
    assert data["order_id"] == order.id
    assert data["status"] == "pending"


async def test_hitl_queue_detail_returns_404_for_missing_item(client):
    _, admin_token = await _seed_admin_with_token()

    response = await client.get("/api/v1/admin/hitl/queue/999999", headers=_auth(admin_token))
    assert response.status_code == 404
    assert response.json()["detail"] == "HITL_ITEM_NOT_FOUND"