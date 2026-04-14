import pytest
from sqlalchemy import select

from sk_shared.models.credit import CreditLimitHistory, RiskAssessment


pytestmark = pytest.mark.asyncio


async def test_credit_apply_success_assigns_limit(client, approved_user):
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
    )

    if response.status_code != 200:
        print(f"DEBUG: Response status {response.status_code}, body: {response.text}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["approved_limit"] is not None


async def test_credit_check_hard_block_rejects_pending_kyc(client, pending_kyc_user):
    response = await client.get(
        "/credit/check",
        params={
            "user_id": str(pending_kyc_user.uuid),
            "order_amount": 2000,
            "product_category": "general",
            "is_first_order": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert "KYC" in data["rejection_reason"]


async def test_credit_check_hard_block_rejects_prohibited_category(client, approved_user):
    response = await client.get(
        "/credit/check",
        params={
            "user_id": str(approved_user.uuid),
            "order_amount": 1200,
            "product_category": "alcohol",
            "is_first_order": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert "prohibited" in data["rejection_reason"].lower()


async def test_admin_override_updates_limit_history(client, approved_user, db_session):
    response = await client.post(
        "/admin/credit/override",
        json={
            "user_id": str(approved_user.uuid),
            "new_limit": 25000,
            "reason_code": "MANUAL_REVIEW_PASS",
            "notes": "Approved by ops",
            "admin_id": "admin-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["new_limit"] == 25000

    query = await db_session.execute(
        select(CreditLimitHistory).where(CreditLimitHistory.user_id == approved_user.uuid)
    )
    history = query.scalars().first()
    assert history is not None
    assert float(history.new_limit) == 25000
    assert history.reason_code == "MANUAL_REVIEW_PASS"


async def test_blacklisted_user_is_rejected(client, approved_user):
    blacklist_response = await client.post(
        "/admin/risk/blacklist",
        json={
            "entity_type": "user",
            "entity_value": str(approved_user.uuid),
            "reason_code": "FRAUD_SIGNAL",
            "severity": "high",
            "blacklisted_by": "fraud-analyst-1",
        },
    )
    assert blacklist_response.status_code == 200

    decision_response = await client.get(
        "/credit/check",
        params={
            "user_id": str(approved_user.uuid),
            "order_amount": 1500,
            "product_category": "general",
            "is_first_order": False,
        },
    )

    assert decision_response.status_code == 200
    body = decision_response.json()
    assert body["approved"] is False
    assert "blacklisted" in body["rejection_reason"].lower()


async def test_risk_alerts_and_explain_endpoints(client, approved_user, db_session):
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
    )
    assert app_response.status_code == 200

    assessment_query = await db_session.execute(
        select(RiskAssessment).where(RiskAssessment.user_id == approved_user.uuid)
    )
    assessment = assessment_query.scalars().first()
    assert assessment is not None

    assessment.risk_band = "F"
    await db_session.commit()

    alerts_response = await client.get("/admin/risk/alerts", params={"limit": 10})
    assert alerts_response.status_code == 200
    alerts_body = alerts_response.json()
    assert isinstance(alerts_body["alerts"], list)
    assert any(item["assessment_id"] == str(assessment.uuid) for item in alerts_body["alerts"])

    explain_response = await client.get(f"/credit/explain/{assessment.uuid}")
    assert explain_response.status_code == 200
    explain_body = explain_response.json()
    assert explain_body["found"] is True
    assert explain_body["assessment_id"] == str(assessment.uuid)
