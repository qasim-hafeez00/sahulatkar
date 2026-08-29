"""
Real, end-to-end order-lifecycle test against the full docker-compose stack:
gateway, product-service (+ its scraping/checkout/vcn-verifier workers),
credit-engine, payment-orchestrator, ledger-service, notification-service,
real Postgres, real Redis, and the mock-merchant fixture -- no per-service
mocking anywhere in this file.

Flow exercised (see tests/e2e/README.md for the full narrative):
  register -> verify OTP -> KYC (auto-approved in local env) ->
  initiate order against the mock merchant -> poll offer ready ->
  accept offer -> generate+sign Wakalah -> generate+sign Murabaha ->
  down payment (JazzCash, synchronous) -> VCN issued ->
  simulate the Stripe Issuing "issuing_transaction.created" webhook that a
  real charge at the merchant would produce (see the note further down on
  why this one signal is simulated rather than organic) ->
  real Playwright checkout against the mock merchant completes ->
  mock-merchant's own /_debug/submissions shows the real submitted data ->
  ledger-service shows a real, balanced journal entry for the down payment.

A handful of internal states (PurchaseExecution.status, VirtualCard's
issuer_card_id) have no customer-facing JSON endpoint to poll -- the task
that produced this suite explicitly sanctions direct Postgres access for
exactly this kind of test-orchestration need (see the late-fee stretch-goal
note about backdating via DB access), so this file opens a plain asyncpg
connection to the same Postgres the stack itself uses, host-mapped on
localhost:5434.
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Any

import asyncpg
import httpx
import pytest

pytestmark = pytest.mark.asyncio

# Matches docker-compose.yml's postgres service (POSTGRES_USER/PASSWORD/DB and
# the 5434:5432 host port mapping) and the PG_PASSWORD default in .env.
_PG_DSN = dict(host="localhost", port=5434, user="sk_admin", password="localdev123", database="sahulatkar")

_MOCK_MERCHANT_PRODUCT_URL = "http://e2e-mock-merchant:8080/product/widget-1"
_EXPECTED_PRICE = 12000.00
_EXPECTED_PRODUCT_NAME = "SahulatKar E2E Test Widget"


def _unique_phone() -> str:
    """A syntactically valid Pakistani E.164 number (^\\+92[0-9]{10}$) that's
    unique per test run, so repeated local runs against a fresh DB never
    collide with a leftover row from a previous run that didn't tear down
    cleanly."""
    digits = "".join(random.choices("0123456789", k=10))
    return f"+92{digits}"


async def _poll_until(fn, predicate, *, timeout: float, interval: float = 2.0, desc: str = "condition"):
    """Poll `fn()` (an async callable) until `predicate(result)` is true, or
    fail loudly with the last observed value once `timeout` elapses. Never
    hangs indefinitely."""
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = await fn()
        if predicate(last):
            return last
        time.sleep(0)  # yield
        await _sleep(interval)
    raise AssertionError(f"Timed out after {timeout}s waiting for: {desc}. Last observed value: {last!r}")


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


async def _db_fetchrow(query: str, *args) -> dict | None:
    conn = await asyncpg.connect(**_PG_DSN)
    try:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def _get_virtual_card(order_id: int) -> dict | None:
    return await _db_fetchrow(
        "SELECT id, issuer_card_id, status, is_used, masked_number "
        "FROM virtual_cards WHERE order_id = $1",
        order_id,
    )


async def _get_purchase_execution(order_id: int) -> dict | None:
    return await _db_fetchrow(
        "SELECT uuid, status, step_reached, merchant_order_id, failure_type, error_detail "
        "FROM purchase_executions WHERE order_id = $1 ORDER BY id DESC LIMIT 1",
        order_id,
    )


async def test_full_order_lifecycle(base_urls: dict[str, str]) -> None:
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=30.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["payment-orchestrator"], timeout=30.0) as pay, \
            httpx.AsyncClient(base_url=base_urls["ledger-service"], timeout=30.0) as ledger, \
            httpx.AsyncClient(base_url=base_urls["e2e-mock-merchant"], timeout=30.0) as merchant:

        # ── 0. Sanity: mock-merchant fixture and product-service can both see it ──
        resp = await merchant.get("/product/widget-1")
        assert resp.status_code == 200
        assert _EXPECTED_PRODUCT_NAME in resp.text

        # ── 1. Register ────────────────────────────────────────────────────────
        phone = _unique_phone()
        resp = await gw.post("/api/v1/auth/register/initiate", json={
            "phone": phone, "first_name": "E2E", "last_name": "Tester",
        })
        assert resp.status_code == 200, resp.text
        initiate_body = resp.json()
        # Local env fixes the registration OTP to "123456" and returns it as
        # dev_otp -- see AuthService.initiate_registration.
        assert initiate_body["dev_otp"] == "123456", initiate_body
        otp_token = initiate_body["otp_token"]

        resp = await gw.post("/api/v1/auth/verify-otp", json={
            "otp_token": otp_token, "otp_code": initiate_body["dev_otp"],
        })
        assert resp.status_code == 200, resp.text
        auth = resp.json()
        access_token = auth["access_token"]
        user_id = auth["user_id"]
        assert auth["kyc_status"] == "pending_kyc", auth

        gw.headers["Authorization"] = f"Bearer {access_token}"

        # ── 2. KYC (auto-approved in local env once NADRA/OCR/liveness mocks pass) ──
        resp = await gw.post("/api/v1/kyc/start")
        assert resp.status_code == 200, resp.text

        resp = await gw.put("/api/v1/kyc/profile", json={
            "first_name": "E2E", "last_name": "Tester",
            "cnic": "12345-1234567-1",  # well-formed, doesn't end in -9 -> NADRA mock approves
            "dob": "1990-01-01T00:00:00",
            "address": "123 Test Street, Karachi",
        })
        assert resp.status_code == 200, resp.text

        for doc_type, filename, content_type in [
            ("cnic_front", "cnic_front.jpg", "image/jpeg"),
            ("cnic_back", "cnic_back.jpg", "image/jpeg"),
            ("liveness_video", "liveness.mp4", "video/mp4"),
        ]:
            # Filenames deliberately avoid "invalid"/"spoof" -- ShuftiClientMock
            # rejects only on those substrings in the stored image/video URL.
            resp = await gw.post(
                f"/api/v1/kyc/upload/{doc_type}",
                files={"file": (filename, b"fake-bytes-for-e2e-test", content_type)},
            )
            assert resp.status_code == 200, resp.text

        resp = await gw.post("/api/v1/kyc/submit")
        assert resp.status_code == 200, resp.text
        kyc = resp.json()
        assert kyc["status"] == "in_review", kyc

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        me = resp.json()
        assert me["status"] == "active", f"KYC auto-approval did not flip the user active: {me}"
        assert me["available_credit"] == pytest.approx(750_000.0), me

        # ── 3. Initiate order against the real mock-merchant product page ───────
        resp = await gw.post("/api/v1/orders/initiate", json={"product_url": _MOCK_MERCHANT_PRODUCT_URL})
        assert resp.status_code == 200, resp.text
        order = resp.json()
        order_id = order["order_id"]
        assert order["status"] == "processing"

        async def _get_offer():
            r = await gw.get(f"/api/v1/orders/{order_id}/offer")
            assert r.status_code == 200, r.text
            return r.json()

        offer = await _poll_until(
            _get_offer,
            lambda o: o["status"] in {"ready", "extraction_failed", "declined"},
            timeout=60.0,
            desc="order offer to leave 'pending' (real cross-service extraction: "
                 "product-service fetches the mock-merchant page, parses JSON-LD, "
                 "calls back to gateway, gateway reserves credit)",
        )
        assert offer["status"] == "ready", f"Extraction did not succeed: {offer}"
        assert offer["product"]["name"] == _EXPECTED_PRODUCT_NAME, offer
        assert offer["product"]["price"] == pytest.approx(_EXPECTED_PRICE), offer
        assert offer["product"]["in_stock"] is True, offer
        assert offer["financing"]["down_payment_pct"] > 0

        # ── 4. Accept offer ───────────────────────────────────────────────────
        resp = await gw.post(f"/api/v1/orders/{order_id}/accept", json={"installment_count": 4})
        assert resp.status_code == 200, resp.text
        accepted = resp.json()
        assert accepted["status"] == "offer_accepted", accepted
        assert accepted["total_amount"] == pytest.approx(_EXPECTED_PRICE), accepted
        down_payment_amount = accepted["down_payment_amount"]
        assert down_payment_amount and down_payment_amount > 0, accepted

        # ── 5. Wakalah agency contract ────────────────────────────────────────
        resp = await gw.post("/api/v1/contracts/wakalah/generate", json={"order_id": order_id})
        assert resp.status_code == 200, resp.text
        wakalah = resp.json()
        assert wakalah["dev_otp"], wakalah
        assert wakalah["authorized_amount"] == pytest.approx(_EXPECTED_PRICE), wakalah

        resp = await gw.post("/api/v1/contracts/wakalah/sign", json={
            "contract_id": wakalah["contract_id"],
            "otp_code": wakalah["dev_otp"],
            "device_id": "e2e-test-device",
        })
        assert resp.status_code == 200, resp.text
        wakalah_signed = resp.json()
        assert wakalah_signed["signed"] is True
        assert wakalah_signed["order_status"] == "contracts_pending", wakalah_signed

        # ── 6. Murabaha sale contract ─────────────────────────────────────────
        resp = await gw.post("/api/v1/contracts/murabaha/generate", json={
            "order_id": order_id, "installment_count": 4,
        })
        assert resp.status_code == 200, resp.text
        murabaha = resp.json()
        assert murabaha["dev_otp"], murabaha
        disclosure = murabaha["disclosure"]
        assert disclosure["total_sale_price"] == pytest.approx(
            disclosure["cost_price"] + disclosure["profit_amount"]
        ), disclosure

        resp = await gw.post("/api/v1/contracts/murabaha/sign", json={
            "contract_id": murabaha["contract_id"],
            "otp_code": murabaha["dev_otp"],
            "confirmation_checkbox": True,
            "device_id": "e2e-test-device",
        })
        assert resp.status_code == 200, resp.text
        murabaha_signed = resp.json()
        assert murabaha_signed["order_status"] == "contracts_signed", murabaha_signed

        # ── 7. Down payment via Payment Orchestrator directly (JazzCash = sync) ──
        idem_key = f"e2e-{uuid.uuid4().hex}"
        resp = await pay.post(
            "/api/v1/payments/down-payment",
            json={
                "order_id": order_id,
                "method": "jazzcash",
                "amount_pkr": str(down_payment_amount),
                "idempotency_key": idem_key,
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200, resp.text
        dp = resp.json()
        assert dp["status"] == "success", dp
        assert dp["gateway_txn_id"], dp

        # ── 8. VCN issuance (queued via outbox -> vcn_issue_worker, all in-process) ──
        async def _get_vcn_status():
            r = await pay.get(
                f"/api/v1/payments/vcn/{order_id}/status",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 404:
                return {"status": "not_issued"}
            assert r.status_code == 200, r.text
            return r.json()

        vcn_status = await _poll_until(
            _get_vcn_status,
            lambda v: v.get("status") not in (None, "not_issued"),
            timeout=60.0,
            desc="VCN to be issued (outbox -> vcn.issue queue -> VcnIssueWorker -> Stripe Issuing local stub)",
        )
        assert vcn_status["status"] == "active", vcn_status

        card = await _poll_until(
            lambda: _get_virtual_card(order_id),
            lambda c: c is not None,
            timeout=15.0,
            desc="virtual_cards row for the order to exist in Postgres",
        )
        assert card["status"] == "active", card

        # ── 9. Simulate the Stripe Issuing "issuing_transaction.created" webhook ──
        #
        # Real-bug note: while building this suite, tracing VcnVerifier.verify_charge
        # (product-service) showed it polls a Redis key
        # ("sk:vcn:charge:confirmed:{vcn_id}") that, before this suite's accompanying
        # fix to VcnOrchestrator.handle_stripe_event, was written by NOTHING anywhere
        # in the codebase -- a real Stripe issuing_transaction.created webhook in
        # production set VirtualCard.is_used and emitted an (unconsumed) vcn.charged
        # event, but never signalled the verifier, so every checkout would time out
        # at "pending_verification" and land on "hitl_escalated" instead of
        # "succeeded", regardless of environment. That's now fixed at the source
        # (apps/payment-orchestrator/src/orchestration/vcn_orchestrator.py).
        #
        # Separately, even with that fixed, this sandboxed stack has no way to
        # organically produce a REAL Stripe webhook: the VCN here is a local stub
        # card (Stripe API calls fail with an invalid key and
        # test_payment_fallbacks_enabled supplies a fake PAN -- see
        # StripeIssuingAdapter.create_card), and the "merchant" is mock_merchant's
        # plain HTML form, not a real card-network acquirer -- there is no real
        # Stripe integration anywhere in this loop for a webhook to come from. So
        # this test does what a real Stripe test-mode integration test would do with
        # `stripe trigger`: POST a synthetic event to payment-orchestrator's own
        # direct webhook endpoint. This exercises the REAL endpoint, REAL card
        # lookup, and the REAL (fixed) Redis signal -- signature verification itself
        # is legitimately skipped only because STRIPE_WEBHOOK_SECRET is unset AND
        # ALLOW_TEST_PAYMENT_FALLBACKS=true (see api/v1/webhooks.py's stripe_webhook
        # handler), the same explicit, fail-closed-everywhere-else opt-in pattern
        # already used for the JazzCash/SafePay/Raast adapters.
        resp = await pay.post("/api/v1/webhooks/stripe", json={
            "id": f"evt_e2e_{uuid.uuid4().hex[:16]}",
            "type": "issuing_transaction.created",
            "data": {
                "object": {
                    "id": f"ipi_e2e_{uuid.uuid4().hex[:16]}",
                    "card": card["issuer_card_id"],
                    "amount": 0,
                }
            },
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok", resp.text

        # ── 10. Real Playwright checkout execution against the mock merchant ────
        # Triggered automatically: payment-orchestrator's VcnService.issue_vcn
        # queued a vcn.issued event -> product-service's in-process
        # EventListenerWorker picked it up -> queued a checkout job ->
        # product-service-checkout-worker ran real Playwright against
        # e2e-mock-merchant -> product-service-vcn-verifier picked up the
        # "pending_verification" job and (now that step 9 supplied the
        # confirmation signal) marks it "succeeded".
        execution = await _poll_until(
            lambda: _get_purchase_execution(order_id),
            lambda e: e is not None and e["status"] in {"succeeded", "failed", "hitl_escalated", "cancelled"},
            timeout=90.0,
            desc="checkout PurchaseExecution to reach a terminal state (real Playwright run against mock-merchant)",
        )
        assert execution["status"] == "succeeded", (
            f"Checkout did not succeed: {execution}. "
            f"(step_reached={execution.get('step_reached')!r}, "
            f"failure_type={execution.get('failure_type')!r}, "
            f"error_detail={execution.get('error_detail')!r})"
        )
        merchant_order_id = execution["merchant_order_id"]
        assert merchant_order_id, execution

        # ── 11. Verify against the merchant's OWN record of what was submitted ──
        # This is the whole point of the mock-merchant fixture: proof that a real
        # browser actually filled in and submitted a real form, not a stub.
        resp = await merchant.get(f"/_debug/submissions/{merchant_order_id}")
        assert resp.status_code == 200, resp.text
        submission = resp.json()
        assert submission["item_id"] == "widget-1", submission
        assert submission["email"] == "customer@sahulatkar.com", submission
        assert submission["city"] == "Karachi", submission
        assert submission["total"] == "12000.00", submission
        assert len(submission["card_last4"]) == 4 and submission["card_last4"].isdigit(), submission

        # ── 12. Ledger shows a real, balanced journal entry for the down payment ──
        resp = await ledger.get(
            "/entries/",
            params={"source_type": "payment.down_payment_confirmed", "limit": 50},
            headers={
                "X-Actor-Type": "admin",
                "X-Actor-Id": "e2e-test",
                "X-Actor-Roles": "super_admin,finance_analyst",
            },
        )
        assert resp.status_code == 200, resp.text
        entries = resp.json()["items"]
        matching = [e for e in entries if e["source_id"] == order_id]
        assert matching, f"No down-payment journal entry found for order {order_id} among {entries}"
        dp_entry = matching[0]
        assert dp_entry["is_balanced"] is True, dp_entry
        assert dp_entry["total_debit"] == dp_entry["total_credit"] == pytest.approx(float(down_payment_amount)), dp_entry
        account_codes = {line["account_code"] for line in dp_entry["lines"]}
        debit_lines = [l for l in dp_entry["lines"] if l["debit_amount"] > 0]
        credit_lines = [l for l in dp_entry["lines"] if l["credit_amount"] > 0]
        assert debit_lines and credit_lines, dp_entry
        assert sum(l["debit_amount"] for l in debit_lines) == pytest.approx(sum(l["credit_amount"] for l in credit_lines)), dp_entry
