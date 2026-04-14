from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.models.kyc import KycStatus, UserKycVerification


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


async def run_identity_signal(db: AsyncSession, user_id: str) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return 0.0, ["invalid_user_id"]

    user_stmt = select(User).where(User.uuid == user_uuid, User.deleted_at == None)  # noqa: E711
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        return 0.0, ["user_not_found"]

    kyc_stmt = (
        select(UserKycVerification)
        .where(UserKycVerification.user_id == user.id)
        .order_by(UserKycVerification.created_at.desc())
    )
    kyc = (await db.execute(kyc_stmt)).scalars().first()
    if not kyc:
        return 0.0, ["kyc_missing"]

    if kyc.status == KycStatus.APPROVED:
        score += 30.0
    else:
        flags.append("kyc_not_approved")

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

    # Reserve fixed bands for future device and VPN signals until device telemetry is wired.
    score += 10.0
    score += 5.0

    if score >= 80:
        flags.append("identity_strong")
    elif score < 60:
        flags.append("identity_weak")

    return round(score, 2), flags
