"""
test_audit_trail.py — Verifies that audit records are created for key financial actions.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from sk_shared.models.audit import AuditTrail

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_vcn_issue_creates_audit_record(client: AsyncClient, test_user, db_session):
    """VCN issue endpoint must emit an audit record before returning."""
    from sk_shared.models.order import Order
    user, token = test_user

    order = Order(user_id=user.id, status="down_payment_received", total_amount=10000, product_description="test")
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id},
        headers=_auth(token),
    )
    assert r.status_code == 200

    records = (
        await db_session.execute(
            select(AuditTrail).where(
                AuditTrail.customer_user_id == user.id,
                AuditTrail.action == "vcn_issue_requested",
            )
        )
    ).scalars().all()
    assert len(records) >= 1


async def test_admin_status_change_creates_audit_record(client: AsyncClient, test_user, test_admin, db_session):
    """Admin user status update must emit an audit record."""
    user, _ = test_user
    _, admin_token = test_admin

    r = await client.put(
        f"/api/v1/admin/users/{user.id}/status",
        json={"status": "suspended"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200

    records = (
        await db_session.execute(
            select(AuditTrail).where(
                AuditTrail.action == "update_status",
                AuditTrail.module == "admin_users",
                AuditTrail.target_id == user.id,
            )
        )
    ).scalars().all()
    assert len(records) >= 1


async def test_down_payment_creates_audit_record(client: AsyncClient, test_user, db_session):
    """Down payment endpoint emits an audit record on success."""
    from sk_shared.models.order import Order
    user, token = test_user

    order = Order(
        user_id=user.id,
        status="contracts_signed",
        total_amount=10000,
        down_payment_amount=2500,
        product_description="test"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    r = await client.post(
        "/api/v1/payments/down-payment",
        json={"order_id": order.id, "method": "safepay", "amount_pkr": "2500.00"},
        headers=_auth(token),
    )
    assert r.status_code == 200

    records = (
        await db_session.execute(
            select(AuditTrail).where(
                AuditTrail.customer_user_id == user.id,
                AuditTrail.action == "down_payment_initiated",
            )
        )
    ).scalars().all()
    assert len(records) >= 1
