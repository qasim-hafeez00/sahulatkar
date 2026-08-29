import json

import pytest
from httpx import AsyncClient
from sk_shared.constants import QueueName
from sk_shared.models.order import Order
from sk_shared.models.order import OrderStatusHistory
from sk_shared.models.payment import Loan, PaymentTransaction

pytestmark = pytest.mark.asyncio

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

async def test_list_admin_orders(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    # 1. Seed some orders
    order1 = Order(user_id=user.id, status="url_received", total_amount=1000)
    order2 = Order(user_id=user.id, status="offer_presented", total_amount=2000)
    db_session.add(order1)
    db_session.add(order2)
    await db_session.commit()
    
    # 2. List
    response = await client.get("/api/v1/admin/orders", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert len(data["orders"]) >= 2
    assert f"ORD-{order1.id}" in [o["order_number"] for o in data["orders"]]

async def test_filter_admin_orders_by_status(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    order = Order(user_id=user.id, status="completed", total_amount=500)
    db_session.add(order)
    await db_session.commit()
    
    # Filter by status
    response = await client.get("/api/v1/admin/orders?status=completed", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    for o in data["orders"]:
        assert o["status"] == "completed"

async def test_admin_override_order_status_accepts_valid_state(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="purchase_failed", total_amount=1500)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    response = await client.put(
        f"/api/v1/admin/orders/{order.id}/status",
        json={"status": "purchasing", "reason": "Manual retry after checkout agent stall"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "purchasing"

    await db_session.refresh(order)
    assert order.status == "purchasing"


async def test_admin_override_order_status_rejects_unknown_state(client: AsyncClient, db_session, test_admin, test_user):
    """P1-07: an unrecognized status string (typo or otherwise) must be
    rejected with a 422, not written straight to Order.status."""
    admin, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="purchase_failed", total_amount=1500)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    response = await client.put(
        f"/api/v1/admin/orders/{order.id}/status",
        json={"status": "purchasingg", "reason": "Typo'd status string"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 422

    await db_session.refresh(order)
    assert order.status == "purchase_failed"


async def test_get_admin_order_detail(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    order = Order(user_id=user.id, status="processing", total_amount=3000)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    
    response = await client.get(f"/api/v1/admin/orders/{order.id}", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["order_number"] == f"ORD-{order.id}"
    assert data["user"]["id"] == user.id

async def test_admin_orders_search_ilike_compatibility(client: AsyncClient, db_session, test_admin, test_user):
    admin, admin_token = test_admin
    user, _ = test_user
    
    order = Order(user_id=user.id, status="url_received", total_amount=100)
    db_session.add(order)
    await db_session.commit()
    
    # Search with different casing to verify LOWER+LIKE fix
    response = await client.get(f"/api/v1/admin/orders?q=ord-{order.id}", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert any(o["order_number"] == f"ORD-{order.id}" for o in data["orders"])


async def test_get_admin_order_timeline(client: AsyncClient, db_session, test_admin, test_user):
    _, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="offer_accepted", total_amount=1200)
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderStatusHistory(order_id=order.id, from_status=None, to_status="url_received", reason="init"))
    db_session.add(OrderStatusHistory(order_id=order.id, from_status="url_received", to_status="offer_accepted", reason="offer"))
    await db_session.commit()

    response = await client.get(f"/api/v1/admin/orders/{order.id}/timeline", headers=_auth(admin_token))
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


async def test_get_admin_order_payments(client: AsyncClient, db_session, test_admin, test_user):
    _, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="contracts_signed", total_amount=5000)
    db_session.add(order)
    await db_session.flush()
    loan = Loan(
        order_id=order.id,
        user_id=user.id,
        loan_number="L-TEST-001",
        principal_amount=4000,
        profit_amount=200,
        total_repayable=4200,
        down_payment_amount=800,
        balance_financed=4000,
        profit_rate_pct=5,
        plan_type="murabaha",
        installment_count=4,
        installment_amount=1050,
        total_paid=0,
        total_outstanding=4200,
        late_fee_total=0,
        status="active",
    )
    db_session.add(loan)
    await db_session.flush()
    db_session.add(
        PaymentTransaction(
            user_id=user.id,
            order_id=order.id,
            loan_id=loan.id,
            amount=800,
            gateway="jazzcash",
            status="confirmed",
            transaction_type="down_payment",
            gateway_txn_id="TXN-001",
        )
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/admin/orders/{order.id}/payments", headers=_auth(admin_token))
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["gateway_txn_id"] == "TXN-001"


async def test_admin_retry_vcn_from_pending_vcn_queues_job(client: AsyncClient, db_session, test_admin, test_user, redis_mock):
    """HIGH-2 regression: an order stuck at 'pending_vcn' (e.g. VcnIssueWorker
    exhausted its retries and DLQ'd the job) must have a real admin recovery
    action, not just the read-only GET .../vcn view. This asserts the retry
    endpoint queues a fresh VCN issuance job and writes an audit trail."""
    admin, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="pending_vcn", total_amount=4200)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    response = await client.post(
        f"/api/v1/admin/orders/{order.id}/retry-vcn",
        json={"reason": "VCN issuance DLQ'd after max retries, retrying manually"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == order.id
    assert data["queued"] is True

    # A fresh job was actually pushed onto the same queue payment-orchestrator's
    # VcnIssueWorker consumes.
    queued = await redis_mock.redis.lrange(QueueName.VCN_ISSUE, 0, -1)
    assert len(queued) == 1
    job = json.loads(queued[0])
    assert job["order_id"] == order.id
    assert job["admin_retry"] is True
    assert job["admin_retry_by"] == admin.id


async def test_admin_retry_vcn_rejects_order_not_stuck(client: AsyncClient, db_session, test_admin, test_user, redis_mock):
    """The retry action must only be usable from 'pending_vcn' -- never from
    an order that already has a card issued or otherwise progressed, to
    avoid double-issuing a VCN."""
    admin, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="vcn_issued", total_amount=4200)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    response = await client.post(
        f"/api/v1/admin/orders/{order.id}/retry-vcn",
        json={"reason": "should not be allowed"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 409

    queued = await redis_mock.redis.lrange(QueueName.VCN_ISSUE, 0, -1)
    assert queued == []


async def test_admin_retry_vcn_404_for_unknown_order(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.post(
        "/api/v1/admin/orders/999999/retry-vcn",
        json={"reason": "order does not exist"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 404


async def test_admin_refund_order_queued(client: AsyncClient, db_session, test_admin, test_user):
    _, admin_token = test_admin
    user, _ = test_user

    order = Order(user_id=user.id, status="delivered", total_amount=2500)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    response = await client.post(
        f"/api/v1/admin/orders/{order.id}/refund",
        json={"reason": "customer return after delivery"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["order_id"] == order.id
    assert data["status"] == "refund_requested"
    assert data["queued"] is True
