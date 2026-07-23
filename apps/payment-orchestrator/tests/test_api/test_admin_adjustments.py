"""
Tests for POST /admin/payments/adjustments.

Phase 2: amount_pkr/reason were originally plain query params on a POST
endpoint that mutates financial state — moved into a Pydantic request body
(AdjustmentRequest) so the request is validated, typed, and doesn't leak
adjustment amounts/reasons into access logs or proxy/URL-length limits.
"""
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from sk_shared.models.auth import AdminUser
from sk_shared.security import create_access_token, get_password_hash
from src.config import settings
from src.main import app

pytestmark = pytest.mark.asyncio


async def _seed_admin(db_session, role: str) -> int:
    admin = AdminUser(
        email=f"{role}@sahulatkar.pk",
        password_hash=get_password_hash("irrelevant"),
        mfa_enabled=False,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin.id


def _admin_token(admin_id: int, role: str) -> str:
    return create_access_token(
        {"admin_id": admin_id, "role": role, "token_type": "admin"},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=900),
    )


async def test_create_adjustment_accepts_body_and_queues_event(client, db_session, seed_order_with_loan):
    order, _loan = await seed_order_with_loan(user_id=1)
    admin_id = await _seed_admin(db_session, "finance")
    token = _admin_token(admin_id, "finance")

    resp = await client.post(
        "/api/v1/admin/payments/adjustments",
        json={"order_id": order.id, "amount_pkr": "150.00", "reason": "goodwill credit"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "queued", "event": "payment.adjustment_requested"}


async def test_create_adjustment_rejects_query_params_without_body(db_session):
    """The old vulnerable shape (query params) must no longer satisfy the
    endpoint's validation — a request with no JSON body is a 422, not a 200."""
    admin_id = await _seed_admin(db_session, "finance")
    token = _admin_token(admin_id, "finance")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/admin/payments/adjustments?order_id=1&amount_pkr=150.00&reason=test",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 422


async def test_create_adjustment_404s_for_order_without_loan(client, db_session):
    admin_id = await _seed_admin(db_session, "finance")
    token = _admin_token(admin_id, "finance")

    resp = await client.post(
        "/api/v1/admin/payments/adjustments",
        json={"order_id": 99999, "amount_pkr": "50.00", "reason": "no such order"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "LOAN_NOT_FOUND_FOR_ORDER"


async def test_create_adjustment_forbidden_for_non_finance_role(client, db_session, seed_order_with_loan):
    order, _loan = await seed_order_with_loan(user_id=2)
    admin_id = await _seed_admin(db_session, "support")
    token = _admin_token(admin_id, "support")

    resp = await client.post(
        "/api/v1/admin/payments/adjustments",
        json={"order_id": order.id, "amount_pkr": "50.00", "reason": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403
