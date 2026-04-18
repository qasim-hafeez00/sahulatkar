import pytest
from httpx import AsyncClient
from sk_shared.models.order import Order
from sk_shared.models.auth import User
import uuid

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_list_admin_orders(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    # 1. Seed some orders
    order1 = Order(order_number="ORD-101", user_id=user.id, status="url_received", total_amount=1000)
    order2 = Order(order_number="ORD-102", user_id=user.id, status="offer_presented", total_amount=2000)
    db_session.add(order1)
    db_session.add(order2)
    await db_session.commit()
    
    # 2. List
    response = await client.get("/api/v1/admin/orders", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) >= 2
    assert "ORD-101" in [o["order_number"] for o in data["orders"]]

async def test_filter_admin_orders_by_status(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    order = Order(order_number="ORD-FILTER", user_id=user.id, status="completed", total_amount=500)
    db_session.add(order)
    await db_session.commit()
    
    # Filter by status
    response = await client.get("/api/v1/admin/orders?status=completed", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    for o in data["orders"]:
        assert o["status"] == "completed"

async def test_get_admin_order_detail(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    order = Order(order_number="ORD-DET-01", user_id=user.id, status="processing", total_amount=3000)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    
    response = await client.get(f"/api/v1/admin/orders/{order.id}", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["order_number"] == "ORD-DET-01"
    assert data["user"]["id"] == user.id

async def test_admin_orders_search_ilike_compatibility(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    order = Order(order_number="CASE-SENSITIVE-SEARCH", user_id=user.id, status="url_received", total_amount=100)
    db_session.add(order)
    await db_session.commit()
    
    # Search with different casing to verify LOWER+LIKE fix
    response = await client.get("/api/v1/admin/orders?q=case-sensitive", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert any(o["order_number"] == "CASE-SENSITIVE-SEARCH" for o in data["orders"])
