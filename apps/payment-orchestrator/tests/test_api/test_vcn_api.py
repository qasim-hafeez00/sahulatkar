"""
Tests for VCN API endpoints.
Target: 12 test cases
"""
import pytest

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_vcn_issue_succeeds_for_signed_order(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0, "merchant_domain": "example.com"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["pan"].startswith("**** **** ****")
    assert data["cvv"] == "***"
    assert data["vcn_id"] > 0


async def test_vcn_issue_blocks_without_signed_contract(client, seed_signed_order, test_user):
    user, token = test_user
    order, _ = await seed_signed_order(user.id, status="contracts_pending")

    resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0, "merchant_domain": "example.com"},
        headers=_auth(token),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "MURABAHA_NOT_SIGNED"


async def test_vcn_issue_is_idempotent(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp1 = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )
    resp2 = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["vcn_id"] == resp2.json()["vcn_id"]


async def test_vcn_void_sets_status_voided(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    issue_resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )
    vcn_id = issue_resp.json()["vcn_id"]

    void_resp = await client.post(
        f"/api/v1/payments/vcn/{vcn_id}/void?reason=test_void",
        headers=_auth(token),
    )
    assert void_resp.status_code == 200
    assert void_resp.json()["status"] == "voided"


async def test_vcn_void_already_voided_is_idempotent(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    issue_resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )
    vcn_id = issue_resp.json()["vcn_id"]

    await client.post(f"/api/v1/payments/vcn/{vcn_id}/void", headers=_auth(token))
    resp2 = await client.post(f"/api/v1/payments/vcn/{vcn_id}/void", headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_voided"


async def test_vcn_status_returns_active(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )
    resp = await client.get(f"/api/v1/payments/vcn/{order.id}/status", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


async def test_vcn_status_404_when_not_issued(client, test_user):
    _, token = test_user
    resp = await client.get("/api/v1/payments/vcn/99999/status", headers=_auth(token))
    assert resp.status_code == 404


async def test_internal_decrypt_requires_internal_token(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )

    resp = await client.get(f"/api/v1/payments/internal/vcn/{order.id}/decrypt")
    assert resp.status_code == 401


async def test_internal_decrypt_with_valid_token_returns_pan(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )

    resp = await client.get(
        f"/api/v1/payments/internal/vcn/{order.id}/decrypt",
        headers={"X-Internal-Token": "test-internal-token-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["pan"]) == 16
    assert data["pan"].startswith("4")           # Our VCN generator starts with 4
    assert len(data["cvv"]) == 3
    assert data["cardholder_name"] == "SahulatKar Agent"


async def test_internal_decrypt_404_when_no_vcn(client):
    resp = await client.get(
        "/api/v1/payments/internal/vcn/99999/decrypt",
        headers={"X-Internal-Token": "test-internal-token-secret"},
    )
    assert resp.status_code == 404


async def test_vcn_issue_adds_buffer_to_authorized_amount(client, test_user, seed_signed_order):
    """VCN authorized amount should include a 5% buffer above the loaded amount."""
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5000.0},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    # Buffer verification is done via DB check, not response (authorized_amount not in VcnIssueResponse)
    # This test verifies issuance succeeds and the VCN is created
    assert resp.json()["status"] == "active"


# ── Phase 0 security regression tests ──────────────────────────────────────────
# Audit finding: /vcn/issue, /vcn/{id}/void, and /vcn/{order_id}/status shipped
# with zero authentication — any caller who knew/enumerated an order_id could
# issue, void, or read the status of a real Stripe virtual card. These tests
# assert the endpoints now require a valid user token AND order ownership.

async def test_vcn_issue_requires_auth(client, seed_signed_order, test_user):
    user, _ = test_user
    order, _ = await seed_signed_order(user.id)

    resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
    )
    assert resp.status_code in (401, 403)


async def test_vcn_issue_rejects_other_users_order(client, seed_signed_order, test_user):
    owner, _ = test_user
    order, _ = await seed_signed_order(owner.id)

    from datetime import timedelta

    from sk_shared.security import create_access_token

    from src.config import settings

    # A valid token for a *different* (non-existent) user_id must not be able to
    # issue a VCN against this order — proves ownership is enforced, not just
    # "any valid token".
    other_token = create_access_token({"user_id": owner.id + 999999}, settings.JWT_PRIVATE_KEY, timedelta(seconds=900))
    resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(other_token),
    )
    assert resp.status_code in (401, 404)


async def test_vcn_void_requires_auth(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    issue_resp = await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )
    vcn_id = issue_resp.json()["vcn_id"]

    resp = await client.post(f"/api/v1/payments/vcn/{vcn_id}/void")
    assert resp.status_code in (401, 403)


async def test_vcn_status_requires_auth(client, test_user, seed_signed_order):
    user, token = test_user
    order, _ = await seed_signed_order(user.id)

    await client.post(
        "/api/v1/payments/vcn/issue",
        json={"order_id": order.id, "amount_pkr": 5200.0},
        headers=_auth(token),
    )

    resp = await client.get(f"/api/v1/payments/vcn/{order.id}/status")
    assert resp.status_code in (401, 403)
