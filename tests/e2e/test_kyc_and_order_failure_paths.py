"""
Real, cross-service tests of the failure/off-ramp branches of the customer
journey that test_order_lifecycle.py's single happy-path run never exercises:
KYC document/identity rejection, the prohibited-category block, extraction
failure, and order cancellation with credit release. Runs against the same
live docker-compose stack (real Postgres, real Redis, real Gateway +
Product Service, the mock-merchant fixture) -- no per-service mocking.

Each test is fully independent (its own unique phone number / customer),
so these can run in any order without interfering with each other or with
test_order_lifecycle.py.
"""
from __future__ import annotations

import httpx
import pytest

from tests.e2e._helpers import (
    WIDGET_URL,
    db_fetchrow,
    poll_until,
    register_and_activate_customer,
    unique_phone,
)

pytestmark = pytest.mark.asyncio


async def _register_only(gw, phone: str) -> dict:
    """Registers + verifies OTP but does not touch KYC. Returns access_token/user_id."""
    resp = await gw.post("/api/v1/auth/register/initiate", json={
        "phone": phone, "first_name": "E2E", "last_name": "FailTester",
    })
    assert resp.status_code == 200, resp.text
    initiate_body = resp.json()

    resp = await gw.post("/api/v1/auth/verify-otp", json={
        "otp_token": initiate_body["otp_token"], "otp_code": initiate_body["dev_otp"],
    })
    assert resp.status_code == 200, resp.text
    auth = resp.json()
    gw.headers["Authorization"] = f"Bearer {auth['access_token']}"
    return auth


async def _upload_kyc_docs(gw, *, front_filename: str, back_filename: str, video_filename: str) -> None:
    for doc_type, filename, content_type in [
        ("cnic_front", front_filename, "image/jpeg"),
        ("cnic_back", back_filename, "image/jpeg"),
        ("liveness_video", video_filename, "video/mp4"),
    ]:
        resp = await gw.post(
            f"/api/v1/kyc/upload/{doc_type}",
            files={"file": (filename, b"fake-bytes-for-e2e-test", content_type)},
        )
        assert resp.status_code == 200, resp.text


async def test_kyc_ocr_failure_blocks_activation(base_urls: dict[str, str]) -> None:
    """ShuftiClientMock.verify_document rejects OCR when the stored
    cnic_front/back URL contains the substring 'invalid' (apps/gateway/src/
    services/shufti.py). Submitting with such a filename must leave the user
    NOT active -- the customer never reaches an order screen."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw:
        await _register_only(gw, unique_phone())

        resp = await gw.post("/api/v1/kyc/start")
        assert resp.status_code == 200, resp.text
        resp = await gw.put("/api/v1/kyc/profile", json={
            "first_name": "E2E", "last_name": "FailTester",
            "cnic": "12345-1234567-1", "dob": "1990-01-01T00:00:00",
            "address": "123 Test Street, Karachi",
        })
        assert resp.status_code == 200, resp.text

        await _upload_kyc_docs(
            gw,
            front_filename="cnic_front_invalid.jpg",  # triggers ShuftiClientMock OCR failure
            back_filename="cnic_back.jpg",
            video_filename="liveness.mp4",
        )

        resp = await gw.post("/api/v1/kyc/submit")
        # OCR failure surfaces either as a non-2xx on submit or as a rejected
        # KYC status -- assert on the durable signal (status), not the HTTP
        # code alone, since both are legitimate designs.
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] in {"rejected", "failed"}, body

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        me = resp.json()
        assert me["status"] != "active", f"OCR failure should not have activated the user: {me}"


async def test_kyc_liveness_failure_blocks_activation(base_urls: dict[str, str]) -> None:
    """ShuftiClientMock.verify_liveness rejects when the stored liveness
    video URL contains 'spoof'."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw:
        await _register_only(gw, unique_phone())

        resp = await gw.post("/api/v1/kyc/start")
        assert resp.status_code == 200, resp.text
        resp = await gw.put("/api/v1/kyc/profile", json={
            "first_name": "E2E", "last_name": "FailTester",
            "cnic": "12345-1234567-1", "dob": "1990-01-01T00:00:00",
            "address": "123 Test Street, Karachi",
        })
        assert resp.status_code == 200, resp.text

        await _upload_kyc_docs(
            gw,
            front_filename="cnic_front.jpg",
            back_filename="cnic_back.jpg",
            video_filename="liveness_spoof.mp4",  # triggers ShuftiClientMock liveness failure
        )

        resp = await gw.post("/api/v1/kyc/submit")
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] in {"rejected", "failed"}, body

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        me = resp.json()
        assert me["status"] != "active", f"Liveness failure should not have activated the user: {me}"


async def test_kyc_nadra_check_runs_against_ocr_extracted_cnic_not_profile_cnic(base_urls: dict[str, str]) -> None:
    """Real finding from building this suite: the documented dev-mode
    shortcut ("a CNIC ending in -9 simulates a NADRA registry mismatch") is
    NOT reachable by submitting that CNIC via PUT /kyc/profile. Tracing
    KycService.submit_for_verification (apps/gateway/src/services/kyc.py)
    shows NADRA is called with `extracted_cnic`, which comes from
    ShuftiClientMock.verify_document's OCR result -- and that mock
    (apps/gateway/src/services/shufti.py) always returns the same
    hardcoded extracted_data.cnic = "12345-1234567-1" (never ending in -9)
    regardless of what CNIC the customer actually entered in their profile
    or what document bytes were uploaded. The profile CNIC is stored and
    displayed but never fed into the NADRA check at all.

    Net effect: as of this writing, there is no way to reach a NADRA
    rejection through the real customer-facing KYC flow -- only through the
    Shufti OCR/liveness branches (see the two tests above) or by calling
    NadraClientMock.verify_cnic directly in a unit test. This test asserts
    the REAL current behavior (submitting a -9 CNIC still succeeds) so it
    fails loudly -- as a deliberate canary, not a false negative -- the day
    someone wires the real submitted/extracted CNIC into this check instead.
    """
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw:
        await _register_only(gw, unique_phone())

        resp = await gw.post("/api/v1/kyc/start")
        assert resp.status_code == 200, resp.text
        resp = await gw.put("/api/v1/kyc/profile", json={
            "first_name": "E2E", "last_name": "FailTester",
            "cnic": "12345-1234569-9",  # ends in -9 -- has NO effect on NADRA verification, see docstring
            "dob": "1990-01-01T00:00:00",
            "address": "123 Test Street, Karachi",
        })
        assert resp.status_code == 200, resp.text

        await _upload_kyc_docs(gw, front_filename="cnic_front.jpg", back_filename="cnic_back.jpg", video_filename="liveness.mp4")

        resp = await gw.post("/api/v1/kyc/submit")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "in_review", resp.json()

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        me = resp.json()
        assert me["status"] == "active", (
            f"Expected the dev-mode auto-approval to activate this user despite the -9 profile "
            f"CNIC (see docstring for why NADRA never actually sees it): {me}"
        )


async def test_order_initiate_blocks_prohibited_category(base_urls: dict[str, str]) -> None:
    """OrderService._check_prohibited_url rejects any product URL containing
    a prohibited keyword (tobacco/alcohol/gambling/...) BEFORE extraction
    even starts -- a fully KYC-active customer should still be blocked."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw:
        await register_and_activate_customer(gw)

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200 and resp.json()["status"] == "active", resp.text

        resp = await gw.post("/api/v1/orders/initiate", json={
            "product_url": "http://e2e-mock-merchant:8080/product/premium-tobacco-widget",
        })
        assert resp.status_code >= 400, f"Prohibited-category URL should have been rejected: {resp.text}"
        assert "PROHIBITED" in resp.text.upper(), resp.text


async def test_order_extraction_failure_reaches_terminal_state(base_urls: dict[str, str]) -> None:
    """A product URL that 404s at the merchant exhausts every extraction
    waterfall tier (apps/product-service/src/services/extraction_waterfall.py)
    and -- with FEATURE_HITL_ESCALATION defaulting True in real deployments,
    not just this test env -- must escalate to a human via a real HitlQueue
    row, not silently vanish or auto-decline.

    BUG FIX found building this test: ProductExtractionService.extract_or_enqueue's
    `hitl_required` branch told the caller "still extracting, check back
    later" but never actually created the HitlQueue row a human needs to act
    on -- unlike the sibling prohibited-category branch a few lines below it,
    which does. Every order whose extraction genuinely exhausted all tiers
    vanished into silent limbo: no admin ever saw it in the HITL queue, and
    the customer's offer only ever left "pending" via Gateway's own 600s
    stuck-order sweep (OrderService.is_stuck_in_extraction) -- far too slow
    to assert on directly in a test, and with no chance of manual recovery
    in the meantime. This test asserts the real, intended terminal signal
    instead: the HitlQueue row itself, same as the admin HITL suite does for
    a checkout-side escalation."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw:
        await register_and_activate_customer(gw)

        resp = await gw.post("/api/v1/orders/initiate", json={
            "product_url": "http://e2e-mock-merchant:8080/product/does-not-exist-in-catalog",
        })
        assert resp.status_code == 200, resp.text
        order_id = resp.json()["order_id"]

        hitl_row = await poll_until(
            lambda: db_fetchrow(
                "SELECT id, status, failure_reason FROM hitl_queue WHERE order_id = $1 ORDER BY id DESC LIMIT 1",
                order_id,
            ),
            lambda r: r is not None,
            timeout=180.0,
            desc="HitlQueue row to be created after all extraction tiers fail for a 404 product URL",
        )
        assert hitl_row["status"] == "pending", hitl_row
        assert "EXTRACTION_FAILED" in (hitl_row["failure_reason"] or ""), hitl_row

        resp = await gw.get(f"/api/v1/orders/{order_id}/offer")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] != "ready", (
            f"A 404 product page should never produce a ready offer: {resp.json()}"
        )

        # NOTE: order.status stays "url_received" here, not "extraction_failed"
        # -- Gateway only flips it via its own 600s stuck-order sweep
        # (OrderService.is_stuck_in_extraction / ORDER_STUCK_EXTRACTION_TIMEOUT_SECONDS),
        # which this test correctly does not wait out. The HitlQueue row
        # above is the real, immediate terminal signal for this path.
        resp = await gw.get(f"/api/v1/orders/{order_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] != "cancelled", resp.json()


async def test_order_cancel_before_payment_releases_credit(base_urls: dict[str, str]) -> None:
    """Cancelling an order after credit has been reserved (post-extraction,
    pre-payment) must restore the customer's available_credit -- this is the
    one release path OrderService documents outside of full loan repayment."""
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw:
        await register_and_activate_customer(gw)

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        credit_before = resp.json()["available_credit"]

        resp = await gw.post("/api/v1/orders/initiate", json={"product_url": WIDGET_URL})
        assert resp.status_code == 200, resp.text
        order_id = resp.json()["order_id"]

        async def _get_offer():
            r = await gw.get(f"/api/v1/orders/{order_id}/offer")
            assert r.status_code == 200, r.text
            return r.json()

        offer = await poll_until(
            _get_offer,
            lambda o: o["status"] in {"ready", "extraction_failed", "declined"},
            timeout=180.0,
            desc="offer to become ready before cancelling",
        )
        assert offer["status"] == "ready", offer

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        credit_after_reservation = resp.json()["available_credit"]
        assert credit_after_reservation < credit_before, (
            f"Credit should have been reserved after extraction: before={credit_before}, "
            f"after={credit_after_reservation}"
        )

        resp = await gw.post(f"/api/v1/orders/{order_id}/cancel")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled", resp.json()

        resp = await gw.get("/api/v1/auth/me")
        assert resp.status_code == 200, resp.text
        credit_after_cancel = resp.json()["available_credit"]
        assert credit_after_cancel == pytest.approx(credit_before), (
            f"Cancelling should have released the reserved credit back: "
            f"before={credit_before}, after_reservation={credit_after_reservation}, "
            f"after_cancel={credit_after_cancel}"
        )
