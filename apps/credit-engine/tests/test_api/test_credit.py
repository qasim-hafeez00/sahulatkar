import uuid
from datetime import date, timedelta

import pytest
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
