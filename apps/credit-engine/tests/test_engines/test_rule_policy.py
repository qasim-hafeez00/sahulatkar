import pytest
from sqlalchemy import delete

from sk_shared.models.credit import CreditPolicyVersion
from src.policy.rule_policy import RulePolicy, RulePolicyLoader

pytestmark = pytest.mark.asyncio


async def test_loader_returns_bootstrap_default_when_no_active_policy(db_session, redis_mock):
    loader = RulePolicyLoader(db_session, redis_mock)
    policy = await loader.load()
    assert policy.version_label == "bootstrap-default"
    assert policy == RulePolicy()


async def test_loader_loads_active_policy_version_from_db(db_session, redis_mock):
    row = CreditPolicyVersion(
        version_label="v2-tighter-alcohol-ban",
        status="active",
        config={"prohibited_categories": ["alcohol", "vapes"], "cold_start_caps": {"A": 5000.0}},
        created_by="test-admin",
    )
    db_session.add(row)
    await db_session.commit()

    loader = RulePolicyLoader(db_session, redis_mock)
    policy = await loader.load()

    assert policy.version_label == "v2-tighter-alcohol-ban"
    assert policy.prohibited_categories == {"alcohol", "vapes"}
    assert policy.cold_start_caps["A"] == 5000.0
    # Fields not overridden by the config JSON keep their bootstrap defaults.
    assert policy.velocity_24h_threshold == RulePolicy().velocity_24h_threshold


async def test_draft_policy_is_ignored_in_favor_of_bootstrap_default(db_session, redis_mock):
    draft = CreditPolicyVersion(
        version_label="v3-draft",
        status="draft",
        config={"prohibited_categories": ["alcohol", "vapes"]},
        created_by="test-admin",
    )
    db_session.add(draft)
    await db_session.commit()

    loader = RulePolicyLoader(db_session, redis_mock)
    policy = await loader.load()
    assert policy.version_label == "bootstrap-default"


async def test_loader_serves_from_redis_cache_without_requerying_db(db_session, redis_mock):
    row = CreditPolicyVersion(
        version_label="v4",
        status="active",
        config={"prohibited_categories": ["alcohol"]},
        created_by="test-admin",
    )
    db_session.add(row)
    await db_session.commit()

    loader = RulePolicyLoader(db_session, redis_mock)
    first = await loader.load()
    assert first.version_label == "v4"

    # If a second load() re-queried the DB instead of using the cache, it would fall back to
    # the bootstrap default here since no active row exists anymore.
    await db_session.execute(delete(CreditPolicyVersion))
    await db_session.commit()

    second = await loader.load()
    assert second.version_label == "v4"
