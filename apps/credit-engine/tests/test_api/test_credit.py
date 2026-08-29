import asyncio
import time
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from sk_shared.models.admin import RiskBlacklist
from sk_shared.models.audit import AuditTrail
from sk_shared.models.credit import (
    BankStatementAnalysis,
    CreditApplication,
    CreditFeatureSnapshot,
    CreditLimitHistory,
    RiskAssessment,
)
from sk_shared.models.payment import Installment, Loan
from src.services.pipeline import CreditPipelineService


pytestmark = pytest.mark.asyncio


async def _seed_verified_bank_statement(db_session, user) -> None:
    """A healthy, salary-verified bank statement — represents an applicant who has actually
    connected real affordability evidence, as opposed to the pure cold-start case (no
    device/IP/bank signal at all) which now caps limits conservatively regardless of score
    band (see Phase 6's data_sparse cold-start cap in LimitEngine.apply_cold_start_cap)."""
    db_session.add(BankStatementAnalysis(
        user_id=user.id,
        period_start=date.today() - timedelta(days=90),
        period_end=date.today(),
        avg_balance=50000.0,
        income_estimate=45000.0,
        expense_ratio=0.35,
        salary_detected=True,
        nsf_events=0,
        source="mock",
    ))
    await db_session.commit()


async def test_credit_apply_success_assigns_limit(client, approved_user, auth_headers):
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 12000,
            "application_type": "manual_request",
            "order_amount": 3000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )

    if response.status_code != 200:
        print(f"DEBUG: Response status {response.status_code}, body: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["approved_limit"] is not None


async def test_credit_check_hard_block_rejects_pending_kyc(client, pending_kyc_user, auth_headers):
    response = await client.get(
        "/credit/check",
        params={
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(pending_kyc_user),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert "KYC" in data["rejection_reason"]


async def test_credit_check_hard_block_rejects_prohibited_category(client, approved_user, auth_headers):
    response = await client.get(
        "/credit/check",
        params={
            "order_amount": 1200,
            "product_category": "alcohol",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert "prohibited" in data["rejection_reason"].lower()


async def test_admin_override_updates_limit_history(client, approved_user, risk_admin, admin_headers, db_session):
    response = await client.post(
        "/admin/credit/override",
        json={
            "user_id": str(approved_user.uuid),
            "new_limit": 25000,
            "reason_code": "MANUAL_REVIEW_PASS",
            "notes": "Approved by ops",
            "admin_id": "admin-1",
        },
        headers=admin_headers(risk_admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["new_limit"] == 25000

    # CreditLimitHistory.user_id is the integer users.id PK (migration 041), not users.uuid —
    # the previous version of this test asserted against .uuid, which is why the underlying
    # bug (passing a UUID into an int column) went undetected as a silent no-op query instead
    # of a hard failure.
    query = await db_session.execute(
        select(CreditLimitHistory).where(CreditLimitHistory.user_id == approved_user.id)
    )
    history = query.scalars().first()
    assert history is not None
    assert float(history.new_limit) == 25000
    assert history.reason_code == "MANUAL_REVIEW_PASS"
    assert history.changed_by == "admin-1"
    assert float(history.available_after) == 25000

    # Phase 7: admin actions on credit-engine used to leave no forensic record at all.
    audit_row = (
        await db_session.execute(
            select(AuditTrail).where(AuditTrail.module == "credit_admin", AuditTrail.action == "override_limit")
        )
    ).scalar_one()
    assert audit_row.admin_user_id == risk_admin.id
    assert audit_row.customer_user_id == approved_user.id
    assert audit_row.changes["new_limit"] == 25000


async def test_blacklisted_user_is_rejected(client, approved_user, risk_admin, auth_headers, admin_headers, db_session):
    blacklist_response = await client.post(
        "/admin/risk/blacklist",
        json={
            "entity_type": "user",
            "entity_value": str(approved_user.uuid),
            "reason_code": "FRAUD_SIGNAL",
            "severity": "high",
            "blacklisted_by": "fraud-analyst-1",
        },
        headers=admin_headers(risk_admin),
    )
    assert blacklist_response.status_code == 200

    # Dual-write reconciliation: gateway's /admin/risk/blacklist UI reads RiskBlacklist, not
    # BlacklistedEntity — confirm the entry landed in both tables, not just credit-engine's own.
    risk_row = (
        await db_session.execute(
            select(RiskBlacklist).where(RiskBlacklist.value == str(approved_user.uuid))
        )
    ).scalar_one_or_none()
    assert risk_row is not None
    assert risk_row.user_id == approved_user.id

    audit_row = (
        await db_session.execute(
            select(AuditTrail).where(AuditTrail.module == "credit_admin", AuditTrail.action == "blacklist_entity")
        )
    ).scalar_one()
    assert audit_row.admin_user_id == risk_admin.id
    assert audit_row.changes["entity_value"] == str(approved_user.uuid)

    decision_response = await client.get(
        "/credit/check",
        params={
            "order_amount": 1500,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )

    assert decision_response.status_code == 200
    body = decision_response.json()
    assert body["approved"] is False
    assert "blacklisted" in body["rejection_reason"].lower()


async def test_risk_alerts_and_explain_endpoints(client, approved_user, risk_admin, auth_headers, admin_headers, db_session):
    app_response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 9000,
            "application_type": "manual_request",
            "order_amount": 2500,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert app_response.status_code == 200

    assessment_query = await db_session.execute(
        select(RiskAssessment).where(RiskAssessment.user_id == approved_user.uuid)
    )
    assessment = assessment_query.scalars().first()
    assert assessment is not None

    assessment.risk_band = "F"
    await db_session.commit()

    admin_hdrs = admin_headers(risk_admin)
    alerts_response = await client.get("/admin/risk/alerts", params={"limit": 10}, headers=admin_hdrs)
    assert alerts_response.status_code == 200
    alerts_body = alerts_response.json()
    assert isinstance(alerts_body["alerts"], list)
    assert any(item["assessment_id"] == str(assessment.uuid) for item in alerts_body["alerts"])

    explain_response = await client.get(f"/credit/explain/{assessment.uuid}", headers=admin_hdrs)
    assert explain_response.status_code == 200
    explain_body = explain_response.json()
    assert explain_body["found"] is True
    assert explain_body["assessment_id"] == str(assessment.uuid)

    # Phase 7: viewing a customer's credit explanation is an admin action worth a forensic
    # record too — "did anyone look at this, and when" used to be unanswerable.
    audit_row = (
        await db_session.execute(
            select(AuditTrail).where(AuditTrail.module == "credit_admin", AuditTrail.action == "view_explanation")
        )
    ).scalar_one()
    assert audit_row.admin_user_id == risk_admin.id
    assert audit_row.target_id == assessment.id


# ── Phase 0 security regression tests ──────────────────────────────────────────
# These endpoints previously had zero authentication wired up at all (audit finding:
# "Zero authentication on every endpoint including /admin/credit/override,
# /admin/risk/blacklist — any network caller can rewrite any user's credit limit or
# blacklist any entity"). Assert every route now rejects unauthenticated callers.

async def test_credit_endpoints_reject_missing_auth(client):
    unauth_cases = [
        ("GET", "/credit/check", {"order_amount": 1000, "product_category": "general"}),
        ("POST", "/credit/apply", {"user_id": str(uuid.uuid4()), "requested_limit": 5000, "order_amount": 1000}),
        ("POST", "/credit/evaluate", {"user_id": str(uuid.uuid4()), "order_amount": 1000}),
        ("POST", "/credit/prequalify", {"user_id": str(uuid.uuid4())}),
        ("GET", "/credit/score", {}),
        ("GET", "/credit/history", {}),
        ("POST", "/credit/recalculate", {}),
        ("GET", "/credit/status", {}),
        ("GET", "/credit/me", {}),
        ("POST", "/admin/credit/override", {"user_id": str(uuid.uuid4()), "new_limit": 5000, "reason_code": "X"}),
        ("POST", "/admin/credit/adjust", {"user_id": str(uuid.uuid4()), "new_limit": 5000, "reason_code": "X"}),
        ("GET", "/admin/risk/alerts", {}),
        ("POST", "/admin/risk/blacklist", {"entity_type": "user", "entity_value": str(uuid.uuid4()), "reason_code": "X"}),
        ("GET", f"/credit/explain/{uuid.uuid4()}", {}),
    ]
    for method, path, payload in unauth_cases:
        if method == "GET":
            response = await client.get(path, params=payload)
        else:
            response = await client.post(path, json=payload)
        assert response.status_code == 401, f"{method} {path} should require auth, got {response.status_code}"


async def test_credit_me_rejects_other_users_token(client, approved_user, pending_kyc_user, auth_headers):
    # A valid token for one user must not let them read another user's credit status.
    response = await client.get("/credit/me", headers=auth_headers(pending_kyc_user))
    assert response.status_code == 200
    assert response.json()["user_id"] == str(pending_kyc_user.uuid)
    assert response.json()["user_id"] != str(approved_user.uuid)


async def test_credit_apply_rejects_mismatched_user_id(client, approved_user, pending_kyc_user, auth_headers):
    # approved_user's token trying to apply for credit under pending_kyc_user's uuid must be forbidden.
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(pending_kyc_user.uuid),
            "requested_limit": 5000,
            "application_type": "manual_request",
            "order_amount": 1000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 403


# ── Phase 4: decision outcomes ───────────────────────────────────────────────────
# approved_user's fixed KYC/identity data alone scores identity=75.2 -> 650 points (Phase 6
# removed the flat, unearned device/VPN trust bonus — see IdentityEngine). Paired with a
# seeded, healthy bank statement (_seed_verified_bank_statement: salary-verified, low
# expense ratio) the blended alt-data score lands at 90 points, for a total of 740 -> band B,
# base_limit=15000, down_payment_pct=25% for "general" category (multiplier 1.0, no
# high-risk bump). Without that bank statement, "bank_data_unavailable" plus no device/IP
# evidence trips the data_sparse cold-start cap regardless of band — see test_prequalify's
# sibling scenarios and LimitEngine.apply_cold_start_cap.

async def test_apply_offers_increase_down_payment_when_order_exceeds_limit(
    client, approved_user, auth_headers, db_session,
):
    await _seed_verified_bank_statement(db_session, approved_user)
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 25000,
            "application_type": "manual_request",
            "order_amount": 25000,  # financed at 25% dp = 18750 > 15000 limit
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "increase_down_payment"
    assert body["status"] == "rejected"
    assert body["suggested_down_payment_pct"] == pytest.approx(40.0)  # 100 * (1 - 15000/25000)


async def test_apply_offers_partial_approval_when_down_payment_bridge_insufficient(
    client, approved_user, auth_headers, db_session,
):
    await _seed_verified_bank_statement(db_session, approved_user)
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 29000,
            "application_type": "manual_request",
            # required down payment to bridge (~48.3%) exceeds the 45% suggestion cap, but the
            # limit still covers >50% of the order, so it's a partial approval, not a reject.
            "order_amount": 29000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "partial_approval"
    assert body["status"] == "approved"
    assert body["approved_limit"] == pytest.approx(15000.0)


async def test_apply_hard_rejects_when_partial_approval_coverage_also_fails(client, approved_user, auth_headers):
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 40000,
            "application_type": "manual_request",
            "order_amount": 40000,  # limit (15000) covers well under half of this
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "rejected"
    assert body["status"] == "rejected"


async def test_apply_caps_limit_for_data_sparse_applicant_despite_repeat_order(client, approved_user, auth_headers):
    # No device fingerprint, no IP data (test client sends none), and no bank statement — the
    # pure cold-start case. Band C's base_limit (8000) would ordinarily apply, but with zero
    # corroborating evidence the data_sparse cap (3000 for band C) takes over even though
    # is_first_order is explicitly False.
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 3000,
            "application_type": "manual_request",
            "order_amount": 3000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_limit"] == pytest.approx(3000.0)


async def test_apply_persists_feature_snapshot_linked_to_assessment_and_strips_it_from_response(
    client, approved_user, auth_headers, db_session,
):
    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 2000,
            "application_type": "manual_request",
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    assert "_feature_snapshot" not in response.json()

    assessment = (
        await db_session.execute(select(RiskAssessment).where(RiskAssessment.user_id == approved_user.uuid))
    ).scalar_one()

    snapshot = (
        await db_session.execute(
            select(CreditFeatureSnapshot).where(CreditFeatureSnapshot.assessment_id == assessment.uuid)
        )
    ).scalar_one()
    assert snapshot.user_id == approved_user.uuid
    assert snapshot.features["order_amount"] == 2000
    assert snapshot.features["policy_version"] == "bootstrap-default"
    assert "identity" in snapshot.features
    assert "scoring" in snapshot.features
    assert snapshot.policy_version == "bootstrap-default"
    assert assessment.explanation["policy_version"] == "bootstrap-default"


async def test_apply_idempotency_key_returns_cached_response_and_avoids_duplicate_application(
    client, approved_user, auth_headers, db_session,
):
    headers = {**auth_headers(approved_user), "Idempotency-Key": "test-idem-key-1"}
    payload = {
        "user_id": str(approved_user.uuid),
        "requested_limit": 9000,
        "application_type": "manual_request",
        "order_amount": 2000,
        "product_category": "general",
        "is_first_order": False,
    }
    first = await client.post("/credit/apply", json=payload, headers=headers)
    second = await client.post("/credit/apply", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    apps = (
        await db_session.execute(select(CreditApplication).where(CreditApplication.user_id == approved_user.uuid))
    ).scalars().all()
    assert len(apps) == 1


async def test_apply_idempotency_key_is_scoped_per_user(
    client, approved_user, pending_kyc_user, auth_headers, db_session,
):
    # Phase 8: the cache key used to be the raw header value with no user scoping — two
    # different callers reusing the same Idempotency-Key string would collide and one user
    # could be served the other's cached decision.
    same_key = "shared-idem-key"
    await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 9000,
            "application_type": "manual_request",
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers={**auth_headers(approved_user), "Idempotency-Key": same_key},
    )
    second_response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(pending_kyc_user.uuid),
            "requested_limit": 9000,
            "application_type": "manual_request",
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers={**auth_headers(pending_kyc_user), "Idempotency-Key": same_key},
    )
    assert second_response.status_code == 200
    # pending_kyc_user's own (rejected) decision, not approved_user's cached approval.
    assert second_response.json()["status"] == "rejected"


async def test_apply_idempotency_key_conflicts_when_a_request_is_already_in_flight(
    client, approved_user, auth_headers, redis_mock,
):
    # Simulates the concurrent-duplicate-submission race: another request already claimed the
    # lock for this key and hasn't finished yet.
    lock_key = f"sk:credit:idempotency:{approved_user.uuid}:racing-key:lock"
    claimed = await redis_mock.set_nx(lock_key, "1", ttl=30)
    assert claimed is True

    response = await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 9000,
            "application_type": "manual_request",
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers={**auth_headers(approved_user), "Idempotency-Key": "racing-key"},
    )
    assert response.status_code == 409


# ── Phase 4: new API surface ──────────────────────────────────────────────────────

async def test_evaluate_endpoint_returns_decision_without_creating_an_application(
    client, approved_user, auth_headers, db_session,
):
    response = await client.post(
        "/credit/evaluate",
        json={
            "user_id": str(approved_user.uuid),
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    assert response.json()["approved"] is True

    apps = (
        await db_session.execute(select(CreditApplication).where(CreditApplication.user_id == approved_user.uuid))
    ).scalars().all()
    assert apps == []


async def test_prequalify_endpoint_returns_indicative_limit(client, approved_user, auth_headers, db_session):
    await _seed_verified_bank_statement(db_session, approved_user)
    response = await client.post(
        "/credit/prequalify",
        json={"user_id": str(approved_user.uuid), "product_category": "general"},
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is True
    assert body["indicative_limit"] == pytest.approx(15000.0)


async def test_prequalify_reports_ineligible_for_prohibited_category(client, approved_user, auth_headers):
    response = await client.post(
        "/credit/prequalify",
        json={"user_id": str(approved_user.uuid), "product_category": "alcohol"},
        headers=auth_headers(approved_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is False
    assert body["indicative_limit"] == 0.0


async def test_score_endpoint_returns_live_score(client, approved_user, auth_headers, db_session):
    await _seed_verified_bank_statement(db_session, approved_user)
    response = await client.get("/credit/score", headers=auth_headers(approved_user))
    assert response.status_code == 200
    body = response.json()
    assert body["risk_band"] == "B"
    assert body["score"] == pytest.approx(740.0)


async def test_history_endpoint_lists_applications(client, approved_user, auth_headers):
    await client.post(
        "/credit/apply",
        json={
            "user_id": str(approved_user.uuid),
            "requested_limit": 9000,
            "application_type": "manual_request",
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
        headers=auth_headers(approved_user),
    )
    response = await client.get("/credit/history", headers=auth_headers(approved_user))
    assert response.status_code == 200
    body = response.json()
    assert len(body["applications"]) == 1
    assert body["applications"][0]["status"] == "approved"


async def test_recalculate_endpoint_reports_delta_against_current_limit(client, approved_user, auth_headers, db_session):
    await _seed_verified_bank_statement(db_session, approved_user)
    response = await client.post("/credit/recalculate", headers=auth_headers(approved_user))
    assert response.status_code == 200
    body = response.json()
    assert body["current_limit"] == 0.0
    assert body["recalculated_limit"] == pytest.approx(15000.0)
    assert body["limit_increased"] is True


# ── Phase 5: rate limiting ────────────────────────────────────────────────────────

async def test_credit_check_rate_limited_after_30_requests_per_minute(client, approved_user, auth_headers):
    headers = auth_headers(approved_user)
    params = {"order_amount": 100, "product_category": "general", "is_first_order": False}

    for _ in range(30):
        response = await client.get("/credit/check", params=params, headers=headers)
        assert response.status_code == 200

    limited = await client.get("/credit/check", params=params, headers=headers)
    assert limited.status_code == 429


async def test_credit_status_is_not_rate_limited(client, approved_user, auth_headers):
    headers = auth_headers(approved_user)
    for _ in range(35):
        response = await client.get("/credit/status", headers=headers)
        assert response.status_code == 200


# ── CE-HIGH-01: portfolio-concentration TOCTOU race ──────────────────────────────
# check_portfolio_concentration (inside evaluate_credit) reads the user's current
# approved exposure, and create_credit_application persists a new approved
# CreditApplication row afterwards. With no lock spanning the two, two concurrent
# /credit/apply calls for the same user could both read the same pre-application
# exposure, both pass the concentration check, and both get approved — jointly
# exceeding the platform's exposure limit for that user. A naive sequential test
# can't catch this: it fires both requests genuinely concurrently via asyncio.gather
# against the same shared db_session/redis_mock the `client` fixture wires up,
# mirroring apps/gateway/tests/test_api/test_orders.py::
# test_concurrent_order_accept_credit_race and the installment double-charge guard
# in payment-orchestrator's payments.py.

async def test_concurrent_credit_apply_serializes_portfolio_concentration_check(
    client, approved_user, auth_headers, db_session,
):
    payload = {
        "user_id": str(approved_user.uuid),
        "requested_limit": 3000,
        "application_type": "manual_request",
        "order_amount": 3000,
        "product_category": "general",
        "is_first_order": False,
    }

    async def apply_once():
        return await client.post("/credit/apply", json=payload, headers=auth_headers(approved_user))

    r1, r2 = await asyncio.gather(apply_once(), apply_once())
    codes = sorted([r1.status_code, r2.status_code])
    # Exactly one request wins the per-user lock and is processed; the other fails
    # fast with 409 instead of racing it and both being approved concurrently.
    assert codes == [200, 409], (
        r1.status_code,
        r1.json() if r1.headers.get("content-type", "").startswith("application/json") else r1.text,
        r2.status_code,
        r2.json() if r2.headers.get("content-type", "").startswith("application/json") else r2.text,
    )

    apps = (
        await db_session.execute(select(CreditApplication).where(CreditApplication.user_id == approved_user.uuid))
    ).scalars().all()
    assert len(apps) == 1


# ── CE-HIGH-02: /credit/apply must not block the response on the Gateway callback ──
# push_credit_result (src/core/http_client.py) retries up to 3x, each with a 5s HTTP
# timeout and exponential backoff between attempts — worst case ~16.5s. Awaiting it
# inline inside create_credit_application used to mean /credit/apply couldn't respond
# until Gateway answered or every retry was exhausted, blowing the endpoint's <3s SLA
# whenever Gateway was slow or down. Mocks the callback to be slow and asserts
# create_credit_application (the code path routes.py's /credit/apply calls) returns
# immediately once a BackgroundTasks is supplied, deferring the callback rather than
# awaiting it.

async def test_create_credit_application_defers_slow_gateway_callback_to_background_task(
    db_session, redis_mock, approved_user,
):
    pipeline = CreditPipelineService(db_session=db_session, redis_client=redis_mock)
    decision = {
        "approved": True,
        "risk_band": "B",
        "approved_limit": 8000.0,
        "rejection_reason": None,
        "outcome": "approved",
        "manual_review_required": False,
    }

    async def _slow_push(**kwargs):
        await asyncio.sleep(0.3)
        return True

    slow_push = AsyncMock(side_effect=_slow_push)
    background_tasks = BackgroundTasks()

    with patch("src.core.http_client.push_credit_result", slow_push):
        start = time.monotonic()
        app = await pipeline.create_credit_application(
            user_id=str(approved_user.uuid),
            requested_limit=8000.0,
            application_type="manual_request",
            decision=decision,
            background_tasks=background_tasks,
        )
        elapsed = time.monotonic() - start

    assert app.status == "approved"
    assert elapsed < 1.0, f"create_credit_application blocked on the Gateway callback ({elapsed:.2f}s)"
    slow_push.assert_not_called()  # not awaited inline
    assert len(background_tasks.tasks) == 1  # scheduled instead, to run after the response

    # Draining the scheduled task the way FastAPI does after sending the response proves
    # the callback isn't silently dropped, just deferred.
    await background_tasks()
    slow_push.assert_awaited_once()


async def test_create_credit_application_awaits_callback_inline_with_no_background_tasks(
    db_session, redis_mock, approved_user,
):
    """The periodic-review worker (workers/credit_assess_consumer.py) calls
    create_credit_application with no FastAPI request/response in play, so there's nothing
    to defer onto — it must keep awaiting the callback synchronously as before."""
    pipeline = CreditPipelineService(db_session=db_session, redis_client=redis_mock)
    decision = {
        "approved": True,
        "risk_band": "B",
        "approved_limit": 8000.0,
        "rejection_reason": None,
        "outcome": "approved",
        "manual_review_required": False,
    }

    fast_push = AsyncMock(return_value=True)
    with patch("src.core.http_client.push_credit_result", fast_push):
        await pipeline.create_credit_application(
            user_id=str(approved_user.uuid),
            requested_limit=8000.0,
            application_type="periodic_review",
            decision=decision,
        )

    fast_push.assert_awaited_once()
