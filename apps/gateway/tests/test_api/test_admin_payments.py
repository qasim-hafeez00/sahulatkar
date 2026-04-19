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


async def test_admin_installments_list_endpoint(client: AsyncClient, db_session, test_admin):
    from sk_shared.models.payment import Loan, Installment
    from sk_shared.models.order import Order

    _, admin_token = test_admin
    user = User(phone="+923001111114", status="active")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    order = Order(user_id=user.id, status="contracts_signed", total_amount=10000, product_description="x")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    loan = Loan(
        order_id=order.id,
        user_id=user.id,
        loan_number="LN-ADMIN-1",
        principal_amount=7000,
        profit_amount=500,
        total_repayable=7500,
        down_payment_amount=2500,
        balance_financed=7000,
        profit_rate_pct=5.0,
        plan_type="standard",
        installment_count=3,
        installment_amount=2500,
        status="active",
        total_paid=0,
        total_outstanding=7500,
        late_fee_total=0,
    )
    db_session.add(loan)
    await db_session.commit()
    await db_session.refresh(loan)

    inst = Installment(
        loan_id=loan.id,
        user_id=user.id,
        installment_number=1,
        is_down_payment=False,
        principal_portion=2300,
        profit_portion=200,
        total_amount=2500,
        due_date=loan.created_at.date(),
        status="pending",
        paid_amount=0,
        days_overdue=0,
        late_fee_amount=0,
        late_fee_waived=False,
        retry_count=0,
    )
    db_session.add(inst)
    await db_session.commit()

    response = await client.get("/api/v1/admin/installments", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert any(item["loan_id"] == loan.id for item in data["items"])


async def test_admin_installments_overdue_filter(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/installments?overdue_only=true", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "overdue"
