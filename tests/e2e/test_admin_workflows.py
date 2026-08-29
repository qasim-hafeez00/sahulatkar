"""
Real, cross-service tests of the ADMIN side of the platform against the same
live docker-compose stack test_order_lifecycle.py uses -- real Postgres,
real Redis, real Gateway, real Product Service (including a real Playwright
checkout run for the HITL scenario). No per-service mocking.

There is no "create the first admin" bootstrap endpoint anywhere in the
codebase (verified while building this suite -- see
_helpers.bootstrap_super_admin's docstring), so this file seeds an AdminUser
directly in Postgres and then drives the real HTTP MFA-setup dance to obtain
a token exactly as production issues one. That direct-DB seed is the same
kind of test-orchestration access test_order_lifecycle.py's own docstring
sanctions for exactly this situation (no API surface exists for it).

Covers: KYC review queue (claim + decision), HITL queue (claim + resolve,
against a REAL checkout failure -- not a synthetic DB row), the risk
blacklist CRUD, and the admin order list/detail views.
"""
from __future__ import annotations

import httpx
import pytest

from tests.e2e._helpers import (
    WIDGET_PRICE_DRIFT_URL,
    bootstrap_super_admin,
    db_fetchrow,
    full_order_to_down_payment,
    get_purchase_execution,
    poll_until,
    register_and_activate_customer,
    unique_phone,
)

pytestmark = pytest.mark.asyncio


async def test_admin_kyc_queue_claim_and_approve(base_urls: dict[str, str]) -> None:
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as admin_client:

        admin = await bootstrap_super_admin(gw)
        admin_client.headers["Authorization"] = f"Bearer {admin['access_token']}"

        customer = await register_and_activate_customer(gw)

        queue_row = await poll_until(
            lambda: db_fetchrow(
                "SELECT q.id FROM kyc_verification_queue q "
                "JOIN user_kyc_verifications k ON k.id = q.kyc_verification_id "
                "WHERE k.user_id = $1 ORDER BY q.id DESC LIMIT 1",
                customer["user_id"],
            ),
            lambda r: r is not None,
            timeout=20.0,
            desc="KYC queue row to appear for the new customer",
        )
        queue_id = queue_row["id"]

        resp = await admin_client.get("/api/v1/admin/kyc/queue", params={"limit": 100})
        assert resp.status_code == 200, resp.text
        assert any(item["id"] == queue_id for item in resp.json()), (
            f"queue_id={queue_id} not present in admin KYC queue listing"
        )

        resp = await admin_client.post(f"/api/v1/admin/kyc/{queue_id}/claim")
        assert resp.status_code == 200, resp.text

        resp = await admin_client.post(f"/api/v1/admin/kyc/{queue_id}/decision", json={"approved": True})
        assert resp.status_code == 200, resp.text
        kyc = resp.json()
        assert kyc.get("status") in {"approved", "APPROVED"}, kyc


async def test_admin_risk_blacklist_add_list_remove(base_urls: dict[str, str]) -> None:
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as admin_client:

        admin = await bootstrap_super_admin(gw)
        admin_client.headers["Authorization"] = f"Bearer {admin['access_token']}"

        phone = unique_phone()
        resp = await admin_client.post("/api/v1/admin/risk/blacklist", json={
            "entry_type": "phone", "value": phone, "reason": "E2E test blacklist entry",
        })
        assert resp.status_code == 201, resp.text
        entry_id = resp.json()["id"]

        resp = await admin_client.get("/api/v1/admin/risk/blacklist", params={"entry_type": "phone"})
        assert resp.status_code == 200, resp.text
        assert any(item["id"] == entry_id for item in resp.json()["items"]), resp.json()

        resp = await admin_client.delete(f"/api/v1/admin/risk/blacklist/{entry_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["removed_id"] == entry_id

        resp = await admin_client.get("/api/v1/admin/risk/blacklist", params={"entry_type": "phone"})
        assert resp.status_code == 200, resp.text
        assert not any(item["id"] == entry_id for item in resp.json()["items"]), (
            "Soft-deleted blacklist entry should no longer be listed"
        )


async def test_admin_orders_list_and_detail(base_urls: dict[str, str]) -> None:
    """Exercises GET /admin/orders and GET /admin/orders/{id} against a real
    order created moments ago -- catches admin-order-list SQL/serialization
    regressions that per-service mocked tests can't (see gateway audit's
    CRITICAL-11 note about this endpoint previously swallowing real SQL
    errors as empty results)."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as admin_client:

        admin = await bootstrap_super_admin(gw)
        admin_client.headers["Authorization"] = f"Bearer {admin['access_token']}"

        customer = await register_and_activate_customer(gw)
        resp = await gw.post("/api/v1/orders/initiate", json={
            "product_url": "http://e2e-mock-merchant:8080/product/widget-1",
        })
        assert resp.status_code == 200, resp.text
        order_id = resp.json()["order_id"]

        resp = await poll_until(
            lambda: admin_client.get("/api/v1/admin/orders", params={"limit": 100}),
            lambda r: r.status_code == 200 and any(o["id"] == order_id for o in r.json()["orders"]),
            timeout=180.0,
            desc=f"order {order_id} to appear in the admin order list",
        )

        resp = await admin_client.get(f"/api/v1/admin/orders/{order_id}")
        assert resp.status_code == 200, resp.text
        detail = resp.json()
        assert detail["id"] == order_id, detail


async def test_admin_hitl_queue_claim_and_resolve_real_checkout_failure(base_urls: dict[str, str]) -> None:
    """Drives a REAL order through down payment + VCN issuance against the
    widget-price-drift mock-merchant fixture, whose cart total is >5% above
    the listing price -- product-service's form_filler.py price-drift check
    (PRICE_DRIFT_THRESHOLD_PCT=5%) then raises PRICE_MISMATCH during the
    real Playwright checkout run, which agent.py._mark_failed escalates to
    a genuine HitlQueue row (status='hitl_escalated' on the
    PurchaseExecution). This test then exercises the admin HITL claim/
    resolve flow against that real row -- not a synthetically inserted one."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["payment-orchestrator"], timeout=180.0) as pay, \
            httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as admin_client:

        admin = await bootstrap_super_admin(gw)
        admin_client.headers["Authorization"] = f"Bearer {admin['access_token']}"

        flow = await full_order_to_down_payment(gw, pay, product_url=WIDGET_PRICE_DRIFT_URL, installment_count=3)
        order_id = flow["order_id"]

        execution = await poll_until(
            lambda: get_purchase_execution(order_id),
            lambda e: e is not None and e["status"] in {"succeeded", "failed", "hitl_escalated", "cancelled"},
            timeout=180.0,
            desc="checkout PurchaseExecution to reach a terminal state on the price-drift fixture",
        )
        assert execution["status"] == "hitl_escalated", (
            f"Expected the price-drift fixture to escalate to HITL: {execution}"
        )
        assert execution["failure_type"] == "price_mismatch", execution

        hitl_row = await poll_until(
            lambda: db_fetchrow(
                "SELECT id, status FROM hitl_queue WHERE order_id = $1 ORDER BY id DESC LIMIT 1",
                order_id,
            ),
            lambda r: r is not None,
            timeout=15.0,
            desc="HitlQueue row to exist for the escalated order",
        )
        queue_id = hitl_row["id"]
        assert hitl_row["status"] == "pending", hitl_row

        resp = await admin_client.get("/api/v1/admin/hitl/queue")
        assert resp.status_code == 200, resp.text
        assert any(item["id"] == queue_id for item in resp.json()["items"]), resp.json()

        resp = await admin_client.post(f"/api/v1/admin/hitl/{queue_id}/claim")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "claimed", resp.json()

        resp = await admin_client.post(
            f"/api/v1/admin/hitl/{queue_id}/resolve",
            json={"resolution": "Manually verified with merchant; price drift was a fixture artifact."},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "resolved", resp.json()
