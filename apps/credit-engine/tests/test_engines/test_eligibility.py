import pytest

from sk_shared.models.admin import RiskBlacklist
from sk_shared.models.credit import BlacklistedEntity
from src.engines.eligibility import EligibilityEngine
from src.policy.rule_policy import RulePolicy


@pytest.mark.asyncio
async def test_prohibited_category_blocks_before_any_db_lookup(db_session, redis_mock, approved_user):
    engine = EligibilityEngine(RulePolicy())
    result = await engine.evaluate(db_session, redis_mock, str(approved_user.uuid), "alcohol")
    assert result.passed is False
    assert result.flags == ["prohibited_category"]


@pytest.mark.asyncio
async def test_clean_approved_user_passes(db_session, redis_mock, approved_user):
    engine = EligibilityEngine(RulePolicy())
    result = await engine.evaluate(db_session, redis_mock, str(approved_user.uuid), "general")
    assert result.passed is True


@pytest.mark.asyncio
async def test_blacklisted_entity_table_hit_blocks(db_session, redis_mock, approved_user):
    db_session.add(BlacklistedEntity(
        entity_type="user",
        entity_value=str(approved_user.uuid),
        reason_code="fraud_suspected",
        severity="high",
        blacklisted_by="risk-analyst",
        is_active=True,
    ))
    await db_session.commit()

    engine = EligibilityEngine(RulePolicy())
    result = await engine.evaluate(db_session, redis_mock, str(approved_user.uuid), "general")
    assert result.passed is False
    assert result.flags == ["blacklist_db_hit"]


@pytest.mark.asyncio
async def test_risk_blacklist_table_hit_also_blocks(db_session, redis_mock, approved_user):
    """RiskBlacklist is the table gateway's /admin/risk/blacklist UI reads and writes — a
    user blacklisted only there (never synced into BlacklistedEntity) must still be blocked
    here, since credit-engine is the reconciled single point of enforcement."""
    db_session.add(RiskBlacklist(
        entry_type="user",
        value=str(approved_user.uuid),
        reason="fraud_suspected (high)",
        user_id=approved_user.id,
    ))
    await db_session.commit()

    engine = EligibilityEngine(RulePolicy())
    result = await engine.evaluate(db_session, redis_mock, str(approved_user.uuid), "general")
    assert result.passed is False
    assert result.flags == ["blacklist_risk_table_hit"]
