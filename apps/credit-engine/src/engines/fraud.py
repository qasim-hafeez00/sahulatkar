from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS
from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.auth import User
from src.core.metrics import credit_fraud_alerts_total
from sk_shared.models.credit import (
    DeviceFingerprint,
    FraudAlert,
    IpIntelligence,
    ManualReviewQueueItem,
    SyntheticIdentityIndicator,
)
from sk_shared.pii import mask_pii_dict
from sk_shared.redis_client import RedisClient
from src.policy.rule_policy import RulePolicy


@dataclass
class FraudResult:
    blocked: bool
    reason: str | None
    flags: list[str] = field(default_factory=list)
    fraud_score: float = 0.0
    manual_review: bool = False
    alert_type: str | None = None
    severity: str | None = None


async def _sliding_window_count(
    redis_client: RedisClient,
    key: str,
    window_seconds: int,
    threshold: int,
) -> tuple[bool, int]:
    now = int(time.time())
    member = f"{now}-{time.monotonic_ns()}"

    # Prefer sorted set sliding window when raw redis client is available.
    if hasattr(redis_client, "redis"):
        raw = redis_client.redis
        await raw.zadd(key, {member: now})
        await raw.zremrangebyscore(key, 0, now - window_seconds)
        count = int(await raw.zcard(key))
        await raw.expire(key, window_seconds)
        return count > threshold, count

    # Fallback for simplified/mocked clients.
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    return count > threshold, count


class FraudEngine:
    """Velocity checks (formerly layer2_velocity.py) plus a composite risk score built from
    device fingerprint, IP reputation, and synthetic-identity signals — the three tables
    migration 014 created but nothing ever read (device_fingerprints, ip_intelligence,
    synthetic_identity_indicators). synthetic_identity_indicators is populated by a separate
    detection job (CNIC/phone/device reuse clustering, etc.); this engine's job is only to
    consume it at decision time, not to compute it.

    Below RulePolicy.fraud_review_threshold the application proceeds untouched. Between the
    review and block thresholds it's flagged manual_review (a FraudAlert + a
    manual_review_queue entry are raised, but the pipeline still completes scoring). At or
    above the block threshold it's a hard reject with a critical FraudAlert.
    """

    def __init__(self, policy: RulePolicy) -> None:
        self.policy = policy

    async def evaluate(
        self,
        db: AsyncSession,
        redis_client: RedisClient,
        user_id: str,
        device_fingerprint_hash: str | None = None,
        ip_address: str | None = None,
    ) -> FraudResult:
        key_24h = f"{RedisNS.CREDIT_VELOCITY}:{user_id}:applications_24h"
        blocked_24h, count_24h = await _sliding_window_count(
            redis_client=redis_client,
            key=key_24h,
            window_seconds=self.policy.velocity_24h_window_seconds,
            threshold=self.policy.velocity_24h_threshold,
        )
        if blocked_24h:
            return FraudResult(True, f"Velocity limit exceeded: {count_24h} applications in 24h", [FlagCode.VELOCITY_24H_BREACH], fraud_score=100.0)

        key_1h = f"{RedisNS.CREDIT_VELOCITY}:{user_id}:applications_1h"
        blocked_1h, count_1h = await _sliding_window_count(
            redis_client=redis_client,
            key=key_1h,
            window_seconds=self.policy.velocity_1h_window_seconds,
            threshold=self.policy.velocity_1h_threshold,
        )
        if blocked_1h:
            return FraudResult(True, f"Velocity limit exceeded: {count_1h} applications in 1h", [FlagCode.VELOCITY_1H_BREACH], fraud_score=100.0)

        user_int_id = await self._resolve_user_int_id(db, user_id)

        risk_score = 0.0
        flags: list[str] = []
        evidence: dict[str, Any] = {}

        if device_fingerprint_hash:
            signal = await self._score_device(db, device_fingerprint_hash)
            if signal is not None:
                risk_score += signal["points"]
                flags.extend(signal["flags"])
                evidence["device"] = signal["evidence"]

        if ip_address:
            signal = await self._score_ip(db, ip_address)
            if signal is not None:
                risk_score += signal["points"]
                flags.extend(signal["flags"])
                evidence["ip"] = signal["evidence"]

        if user_int_id is not None:
            signal = await self._score_synthetic_identity(db, user_int_id)
            if signal is not None:
                risk_score += signal["points"]
                flags.extend(signal["flags"])
                evidence["synthetic_identity"] = signal["evidence"]

        alert_type = self._infer_alert_type(evidence)

        if risk_score >= self.policy.fraud_block_threshold:
            if user_int_id is not None:
                await self._raise_fraud_alert(db, user_int_id, alert_type, "critical", risk_score, evidence)
            return FraudResult(
                blocked=True,
                reason=f"Fraud risk score {risk_score:.0f} exceeded block threshold",
                flags=flags + [FlagCode.FRAUD_SCORE_BLOCKED],
                fraud_score=risk_score,
                alert_type=alert_type,
                severity="critical",
            )

        if risk_score >= self.policy.fraud_review_threshold:
            if user_int_id is not None:
                await self._raise_fraud_alert(db, user_int_id, alert_type, "medium", risk_score, evidence)
                await self._enqueue_manual_review(db, user_int_id, risk_score, evidence)
            return FraudResult(
                blocked=False,
                reason=f"Fraud risk score {risk_score:.0f} requires manual review",
                flags=flags + [FlagCode.MANUAL_REVIEW_REQUIRED, FlagCode.VELOCITY_CLEAR],
                fraud_score=risk_score,
                manual_review=True,
                alert_type=alert_type,
                severity="medium",
            )

        return FraudResult(False, None, flags + [FlagCode.VELOCITY_CLEAR], fraud_score=risk_score)

    @staticmethod
    def _infer_alert_type(evidence: dict[str, Any]) -> str:
        if "synthetic_identity" in evidence:
            return "synthetic_identity"
        if "device" in evidence:
            return "device_anomaly"
        if "ip" in evidence:
            return "cross_border_risk"
        return "velocity_breach"

    async def _resolve_user_int_id(self, db: AsyncSession, user_id: str) -> int | None:
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            return None
        return (await db.execute(select(User.id).where(User.uuid == user_uuid))).scalar_one_or_none()

    async def _score_device(self, db: AsyncSession, device_fingerprint_hash: str) -> dict[str, Any] | None:
        stmt = (
            select(DeviceFingerprint)
            .where(DeviceFingerprint.computed_hash == device_fingerprint_hash)
            .order_by(DeviceFingerprint.computed_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        points = 0.0
        flags: list[str] = []
        if row.is_known_fraud_device:
            points += self.policy.device_known_fraud_points
            flags.append(FlagCode.KNOWN_FRAUD_DEVICE)
        for risk_flag in row.risk_flags or []:
            points += self.policy.device_risk_flag_points.get(risk_flag, 0.0)
        if points > 0:
            flags.append(FlagCode.DEVICE_RISK_SIGNAL)

        return {
            "points": points,
            "flags": flags,
            "evidence": {
                "computed_hash": device_fingerprint_hash,
                "risk_flags": row.risk_flags or [],
                "is_known_fraud_device": row.is_known_fraud_device,
            },
        }

    async def _score_ip(self, db: AsyncSession, ip_address: str) -> dict[str, Any] | None:
        stmt = select(IpIntelligence).where(IpIntelligence.ip == ip_address)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None

        points = 0.0
        flags: list[str] = []
        if row.is_tor:
            points += self.policy.ip_tor_points
            flags.append(FlagCode.TOR_EXIT_NODE)
        elif row.is_proxy:
            points += self.policy.ip_proxy_points
            flags.append(FlagCode.PROXY_DETECTED)
        elif row.is_vpn:
            points += self.policy.ip_vpn_points
            flags.append(FlagCode.VPN_DETECTED)

        threat_score = float(row.threat_score) if row.threat_score is not None else 0.0
        points += threat_score * self.policy.ip_threat_score_weight

        return {
            "points": points,
            "flags": flags,
            "evidence": {
                "ip": ip_address,
                "is_tor": row.is_tor,
                "is_proxy": row.is_proxy,
                "is_vpn": row.is_vpn,
                "threat_score": threat_score,
                "country": row.country,
            },
        }

    async def _score_synthetic_identity(self, db: AsyncSession, user_int_id: int) -> dict[str, Any] | None:
        stmt = (
            select(SyntheticIdentityIndicator)
            .where(SyntheticIdentityIndicator.user_id == user_int_id)
            .order_by(SyntheticIdentityIndicator.flagged_at.desc())
            .limit(5)
        )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            return None

        top_confidence = max(float(r.confidence_score) for r in rows)
        points = top_confidence * self.policy.synthetic_identity_weight
        return {
            "points": points,
            "flags": [FlagCode.SYNTHETIC_IDENTITY_SIGNAL],
            "evidence": {
                "indicator_types": [r.indicator_type for r in rows],
                "top_confidence": top_confidence,
                # supporting_signals is written by the (separate) synthetic-identity
                # detection job and may include the raw CNIC/phone value it matched a reuse
                # on. Left unmasked here (in-memory, this request only) — _raise_fraud_alert
                # / _enqueue_manual_review mask the whole evidence dict exactly once, at the
                # point it's actually persisted/logged.
                "supporting_signals": [r.supporting_signals for r in rows if r.supporting_signals],
            },
        }

    async def _raise_fraud_alert(
        self,
        db: AsyncSession,
        user_int_id: int,
        alert_type: str,
        severity: str,
        risk_score: float,
        evidence: dict[str, Any],
    ) -> None:
        alert = FraudAlert(
            user_id=user_int_id,
            alert_type=alert_type,
            severity=severity,
            source="rule_engine",
            rule_code="composite_fraud_score",
            description=f"Composite fraud risk score {risk_score:.1f}",
            evidence=mask_pii_dict(evidence),
            status="open",
        )
        db.add(alert)
        await db.commit()
        credit_fraud_alerts_total.labels(severity=severity).inc()

    async def _enqueue_manual_review(
        self,
        db: AsyncSession,
        user_int_id: int,
        risk_score: float,
        evidence: dict[str, Any],
    ) -> None:
        item = ManualReviewQueueItem(
            entity_type="user",
            entity_id=user_int_id,
            queue_type="fraud_review",
            priority=2,
            status="pending",
            sla_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
            notes=f"Composite fraud risk score {risk_score:.1f}. Evidence: {mask_pii_dict(evidence)}",
        )
        db.add(item)
        await db.commit()
