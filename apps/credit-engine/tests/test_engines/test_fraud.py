import pytest
from sqlalchemy import select

from sk_shared.models.credit import (
    DeviceFingerprint,
    FraudAlert,
    IpIntelligence,
    ManualReviewQueueItem,
    SyntheticIdentityIndicator,
)
from src.engines.fraud import FraudEngine
from src.policy.rule_policy import RulePolicy


@pytest.mark.asyncio
async def test_no_signal_data_leaves_score_at_zero(db_session, redis_mock, approved_user):
    engine = FraudEngine(RulePolicy())
    result = await engine.evaluate(db_session, redis_mock, str(approved_user.uuid))
    assert result.blocked is False
    assert result.manual_review is False
    assert result.fraud_score == 0.0
    assert "velocity_clear" in result.flags


@pytest.mark.asyncio
async def test_known_fraud_device_with_risk_flags_triggers_block(db_session, redis_mock, approved_user):
    device = DeviceFingerprint(
        user_id=approved_user.id,
        raw_fingerprint={"ua": "test-agent"},
        computed_hash="deadbeef",
        risk_flags=["emulator"],
        is_known_fraud_device=True,
    )
    db_session.add(device)
    await db_session.commit()

    engine = FraudEngine(RulePolicy())
    result = await engine.evaluate(
        db_session, redis_mock, str(approved_user.uuid), device_fingerprint_hash="deadbeef",
    )

    assert result.blocked is True
    assert result.fraud_score == pytest.approx(95.0)  # 60 known-fraud + 35 emulator
    assert "fraud_score_blocked" in result.flags

    alerts = (await db_session.execute(select(FraudAlert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
    assert alerts[0].alert_type == "device_anomaly"
    assert alerts[0].user_id == approved_user.id


@pytest.mark.asyncio
async def test_vpn_ip_with_high_threat_score_triggers_manual_review(db_session, redis_mock, approved_user):
    ip_row = IpIntelligence(ip="203.0.113.5", is_vpn=True, threat_score=0.9)
    db_session.add(ip_row)
    await db_session.commit()

    engine = FraudEngine(RulePolicy())
    result = await engine.evaluate(
        db_session, redis_mock, str(approved_user.uuid), ip_address="203.0.113.5",
    )

    assert result.blocked is False
    assert result.manual_review is True
    assert result.fraud_score == pytest.approx(46.0)  # 10 vpn + 0.9*40 threat
    assert "manual_review_required" in result.flags

    queue_items = (await db_session.execute(select(ManualReviewQueueItem))).scalars().all()
    assert len(queue_items) == 1
    assert queue_items[0].entity_id == approved_user.id
    assert queue_items[0].queue_type == "fraud_review"
    assert queue_items[0].status == "pending"

    alerts = (await db_session.execute(select(FraudAlert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].severity == "medium"
    assert alerts[0].alert_type == "cross_border_risk"


@pytest.mark.asyncio
async def test_synthetic_identity_indicator_alone_can_trigger_review(db_session, redis_mock, approved_user):
    indicator = SyntheticIdentityIndicator(
        user_id=approved_user.id,
        indicator_type="device_reuse",
        confidence_score=0.5,
    )
    db_session.add(indicator)
    await db_session.commit()

    engine = FraudEngine(RulePolicy())
    result = await engine.evaluate(db_session, redis_mock, str(approved_user.uuid))

    assert result.manual_review is True
    assert result.fraud_score == pytest.approx(50.0)  # 0.5 confidence * 100 weight
    assert result.alert_type == "synthetic_identity"


@pytest.mark.asyncio
async def test_synthetic_identity_supporting_signals_are_pii_masked_in_stored_evidence(
    db_session, redis_mock, approved_user,
):
    db_session.add(SyntheticIdentityIndicator(
        user_id=approved_user.id,
        indicator_type="phone_reuse",
        confidence_score=0.9,
        supporting_signals={"phone": "+923001234567", "note": "shared across 3 accounts"},
    ))
    await db_session.commit()

    engine = FraudEngine(RulePolicy())
    await engine.evaluate(db_session, redis_mock, str(approved_user.uuid))

    alert = (await db_session.execute(select(FraudAlert))).scalars().one()
    stored_signals = alert.evidence["synthetic_identity"]["supporting_signals"][0]
    assert stored_signals["phone"] == "92********67"
    assert stored_signals["note"] == "shared across 3 accounts"


@pytest.mark.asyncio
async def test_low_risk_vpn_alone_stays_below_review_threshold(db_session, redis_mock, approved_user):
    ip_row = IpIntelligence(ip="198.51.100.9", is_vpn=True, threat_score=0.1)
    db_session.add(ip_row)
    await db_session.commit()

    engine = FraudEngine(RulePolicy())
    result = await engine.evaluate(
        db_session, redis_mock, str(approved_user.uuid), ip_address="198.51.100.9",
    )

    assert result.blocked is False
    assert result.manual_review is False
    assert result.fraud_score == pytest.approx(14.0)  # 10 vpn + 0.1*40 threat
    assert (await db_session.execute(select(FraudAlert))).scalars().all() == []
