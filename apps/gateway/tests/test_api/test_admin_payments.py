import pytest
from httpx import AsyncClient
from sk_shared.models.payment import PaymentTransaction
from sk_shared.models.auth import User

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_list_admin_payments(client: AsyncClient, db_session, test_admin):
    _, admin_token = test_admin
    user = User(phone="+923001111111", status="active")
    db_session.add(user)
    await db_session.commit()
    
    # 1. Seed payments
    p1 = PaymentTransaction(
        user_id=user.id,
        gateway_txn_id="TXN-101",
        amount=500.0,
        currency="PKR",
        status="confirmed",
        gateway="jazzcash",
        order_id=1
    )
    p2 = PaymentTransaction(
        user_id=user.id,
        gateway_txn_id="TXN-102",
        amount=1000.0,
        currency="PKR",
        status="pending",
        gateway="easypaisa",
        order_id=2
    )
    db_session.add(p1)
    db_session.add(p2)
    await db_session.commit()
    
    # 2. List
    response = await client.get("/api/v1/admin/payments", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert len(data["payments"]) >= 2
    assert "TXN-101" in [p["transaction_id"] for p in data["payments"]]

async def test_get_admin_payment_detail(client: AsyncClient, db_session, test_admin):
    _, admin_token = test_admin
    user = User(phone="+923001111112", status="active")
    db_session.add(user)
    await db_session.commit()
    
    p = PaymentTransaction(
        user_id=user.id,
        gateway_txn_id="TXN-DET-1",
        amount=1500.0,
        status="failed",
        failure_code="INSUFFICIENT_FUNDS",
        failure_message="Not enough balance",
        gateway="manual",
        order_id=3
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    
    response = await client.get(f"/api/v1/admin/payments/{p.id}", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["transaction_id"] == "TXN-DET-1"
    assert data["error"]["code"] == "INSUFFICIENT_FUNDS"

async def test_filter_admin_payments_by_gateway(client: AsyncClient, db_session, test_admin):
    _, admin_token = test_admin
    user = User(phone="+923001111113", status="active")
    db_session.add(user)
    await db_session.commit()
    
    p = PaymentTransaction(user_id=user.id, gateway_txn_id="TXN-GW", gateway="manual", amount=100, order_id=4)
    db_session.add(p)
    await db_session.commit()
    
    response = await client.get("/api/v1/admin/payments?gateway=manual", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    for p in data["payments"]:
        assert p["gateway"] == "manual"
