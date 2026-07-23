from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.auth import User
from sk_shared.models.credit import DeviceFingerprint, IpIntelligence
from sk_shared.models.kyc import KycStatus, UserKycVerification


@dataclass
class IdentityResult:
    score: float
    flags: list[str] = field(default_factory=list)


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class IdentityEngine:
    """NADRA/Shufti verification confidence -> a 0-100 trust score. Formerly
    layer3_identity.py, split out so it composes independently in the engine pipeline and its
    score contribution is directly usable by ExplanationBuilder.

    The device/IP trust component (up to 15 of the 100 points) is only awarded when there is
    an actual clean DeviceFingerprint/IpIntelligence row to back it — it used to be a flat
    bonus handed to every applicant regardless of whether that evidence existed, which meant a
    fraudster who left zero device/IP footprint scored identically to one who had passed real
    checks. Cold-start applicants (no device/IP data at all) now simply don't earn those
    points, rather than being credited with unverified trust — a lower score for an unverified
    profile, not a fraud accusation for one."""

    async def evaluate(
        self,
        db: AsyncSession,
        user_id: str,
        device_fingerprint_hash: str | None = None,
        ip_address: str | None = None,
    ) -> IdentityResult:
        flags: list[str] = []
        score = 0.0

        try:
            user_uuid = UUID(user_id)
        except ValueError:
            return IdentityResult(0.0, [FlagCode.INVALID_USER_ID])

        user_stmt = select(User).where(User.uuid == user_uuid, User.deleted_at == None)  # noqa: E711
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        if not user:
            return IdentityResult(0.0, [FlagCode.USER_NOT_FOUND])

        kyc_stmt = (
            select(UserKycVerification)
            .where(UserKycVerification.user_id == user.id)
            .order_by(UserKycVerification.created_at.desc())
        )
        kyc = (await db.execute(kyc_stmt)).scalars().first()
        if not kyc:
            return IdentityResult(0.0, [FlagCode.KYC_MISSING])

        if kyc.status == KycStatus.APPROVED:
            score += 30.0
        else:
            flags.append(FlagCode.KYC_NOT_APPROVED)

        nadra_data = kyc.nadra_verification_data or {}
        shufti_data = kyc.shufti_verification_data or {}

        nadra_confidence = _to_float(nadra_data.get("confidence"), default=0.0)
        score += min(max(nadra_confidence, 0.0), 1.0) * 20.0

        face_match = _to_float(shufti_data.get("face_match_score"), default=0.0)
        score += min(max(face_match, 0.0), 1.0) * 20.0

        liveness = _to_float(shufti_data.get("liveness_score"), default=0.0)
        score += min(max(liveness, 0.0), 1.0) * 10.0

        if user.created_at:
            created_at = user.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_old = (now - created_at).days
            tenure_ratio = min(max(days_old / 365.0, 0.0), 1.0)
            score += tenure_ratio * 5.0

        device_trust = await self._score_device_trust(db, device_fingerprint_hash)
        score += device_trust
        flags.append(FlagCode.DEVICE_TRUSTED if device_trust > 0 else FlagCode.DEVICE_TRUST_UNVERIFIED)

        ip_trust = await self._score_ip_trust(db, ip_address)
        score += ip_trust
        flags.append(FlagCode.IP_TRUSTED if ip_trust > 0 else FlagCode.IP_TRUST_UNVERIFIED)

        if score >= 80:
            flags.append(FlagCode.IDENTITY_STRONG)
        elif score < 60:
            flags.append(FlagCode.IDENTITY_WEAK)

        return IdentityResult(round(score, 2), flags)

    @staticmethod
    async def _score_device_trust(db: AsyncSession, device_fingerprint_hash: str | None) -> float:
        if not device_fingerprint_hash:
            return 0.0
        stmt = (
            select(DeviceFingerprint)
            .where(DeviceFingerprint.computed_hash == device_fingerprint_hash)
            .order_by(DeviceFingerprint.computed_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None or row.is_known_fraud_device or row.risk_flags:
            return 0.0
        return 10.0

    @staticmethod
    async def _score_ip_trust(db: AsyncSession, ip_address: str | None) -> float:
        if not ip_address:
            return 0.0
        stmt = select(IpIntelligence).where(IpIntelligence.ip == ip_address)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None or row.is_tor or row.is_proxy or row.is_vpn:
            return 0.0
        threat_score = float(row.threat_score) if row.threat_score is not None else 0.0
        if threat_score >= 0.3:
            return 0.0
        return 5.0
