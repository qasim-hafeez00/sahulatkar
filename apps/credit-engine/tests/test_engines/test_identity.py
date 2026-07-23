import pytest

from sk_shared.models.credit import DeviceFingerprint, IpIntelligence
from src.engines.identity import IdentityEngine


@pytest.mark.asyncio
async def test_no_device_or_ip_evidence_earns_no_trust_bonus(db_session, approved_user):
    # Phase 6: this used to be a flat +15 handed to every applicant regardless of evidence —
    # a fraudster with zero device/IP footprint scored identically to a verified-clean one.
    engine = IdentityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid))
    assert result.score == pytest.approx(75.2)  # 30 kyc + 18.4 nadra + 18 face + 8.8 liveness
    assert "device_trust_unverified" in result.flags
    assert "ip_trust_unverified" in result.flags


@pytest.mark.asyncio
async def test_clean_device_fingerprint_earns_trust_bonus(db_session, approved_user):
    db_session.add(DeviceFingerprint(
        user_id=approved_user.id,
        raw_fingerprint={"ua": "test-agent"},
        computed_hash="clean-device-hash",
        risk_flags=[],
        is_known_fraud_device=False,
    ))
    await db_session.commit()

    engine = IdentityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid), device_fingerprint_hash="clean-device-hash")
    assert result.score == pytest.approx(85.2)  # 75.2 + 10 device trust
    assert "device_trusted" in result.flags


@pytest.mark.asyncio
async def test_known_fraud_device_earns_no_trust_bonus(db_session, approved_user):
    db_session.add(DeviceFingerprint(
        user_id=approved_user.id,
        raw_fingerprint={"ua": "test-agent"},
        computed_hash="risky-device-hash",
        risk_flags=["emulator"],
        is_known_fraud_device=True,
    ))
    await db_session.commit()

    engine = IdentityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid), device_fingerprint_hash="risky-device-hash")
    assert result.score == pytest.approx(75.2)
    assert "device_trust_unverified" in result.flags


@pytest.mark.asyncio
async def test_clean_ip_earns_trust_bonus(db_session, approved_user):
    db_session.add(IpIntelligence(ip="10.0.0.1", is_vpn=False, is_proxy=False, is_tor=False, threat_score=0.05))
    await db_session.commit()

    engine = IdentityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid), ip_address="10.0.0.1")
    assert result.score == pytest.approx(80.2)  # 75.2 + 5 ip trust
    assert "ip_trusted" in result.flags


@pytest.mark.asyncio
async def test_vpn_ip_earns_no_trust_bonus(db_session, approved_user):
    db_session.add(IpIntelligence(ip="10.0.0.2", is_vpn=True, is_proxy=False, is_tor=False, threat_score=0.05))
    await db_session.commit()

    engine = IdentityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid), ip_address="10.0.0.2")
    assert result.score == pytest.approx(75.2)
    assert "ip_trust_unverified" in result.flags


@pytest.mark.asyncio
async def test_unknown_ip_with_no_intelligence_row_earns_no_trust_bonus(db_session, approved_user):
    engine = IdentityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid), ip_address="203.0.113.99")
    assert result.score == pytest.approx(75.2)
    assert "ip_trust_unverified" in result.flags
