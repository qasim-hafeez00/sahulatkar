from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS
from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.admin import RiskBlacklist
from sk_shared.models.auth import User
from sk_shared.models.credit import BlacklistedEntity
from sk_shared.models.kyc import KycStatus, UserKycVerification
from sk_shared.redis_client import RedisClient
from src.policy.rule_policy import RulePolicy


@dataclass
class EligibilityResult:
    passed: bool
    reason: str | None
    flags: list[str] = field(default_factory=list)


class EligibilityEngine:
    """Hard blocks: KYC status, blacklist membership, prohibited product category, account
    status. Formerly layer1_hard_blocks.py — the prohibited-category set now comes from
    RulePolicy instead of a module-level constant duplicated in the limit engine.

    Blacklist membership is checked against both BlacklistedEntity (credit-engine's original
    table) and RiskBlacklist (the table gateway's /admin/risk/blacklist UI actually reads and
    writes) — the two never synced, so a user blacklisted through either surface is now
    blocked here regardless of which table holds the row."""

    def __init__(self, policy: RulePolicy) -> None:
        self.policy = policy

    async def evaluate(
        self,
        db: AsyncSession,
        redis_client: RedisClient,
        user_uuid: str,
        product_category: str | None = None,
    ) -> EligibilityResult:
        if product_category and product_category.strip().lower() in self.policy.prohibited_categories:
            return EligibilityResult(False, "Prohibited product category", [FlagCode.PROHIBITED_CATEGORY])

        blacklist_key = f"{RedisNS.CREDIT_BLACKLIST}:user:{user_uuid}"
        cached_blacklist = await redis_client.get(blacklist_key)
        if cached_blacklist:
            return EligibilityResult(False, "User is blacklisted", [FlagCode.BLACKLIST_CACHE_HIT])

        blacklist_stmt = select(BlacklistedEntity).where(
            and_(
                BlacklistedEntity.entity_type == "user",
                BlacklistedEntity.entity_value == user_uuid,
                BlacklistedEntity.is_active.is_(True),
            )
        )
        blacklist_row = (await db.execute(blacklist_stmt)).scalar_one_or_none()
        if blacklist_row:
            if blacklist_row.expires_at is None or blacklist_row.expires_at > datetime.now(timezone.utc):
                await redis_client.set(blacklist_key, "1", ttl=3600)
                return EligibilityResult(False, "User is blacklisted", [FlagCode.BLACKLIST_DB_HIT])

        risk_blacklist_stmt = select(RiskBlacklist).where(
            and_(
                RiskBlacklist.entry_type == "user",
                RiskBlacklist.value == user_uuid,
                RiskBlacklist.deleted_at.is_(None),
            )
        )
        risk_blacklist_row = (await db.execute(risk_blacklist_stmt)).scalar_one_or_none()
        if risk_blacklist_row:
            await redis_client.set(blacklist_key, "1", ttl=3600)
            return EligibilityResult(False, "User is blacklisted", [FlagCode.BLACKLIST_RISK_TABLE_HIT])

        try:
            user_uuid_obj = UUID(user_uuid)
        except ValueError:
            return EligibilityResult(False, "Invalid user id", [FlagCode.INVALID_USER_ID])

        user_stmt = select(User).where(User.uuid == user_uuid_obj, User.deleted_at == None)  # noqa: E711
        user = (await db.execute(user_stmt)).scalar_one_or_none()
        if not user:
            return EligibilityResult(False, "User not found", [FlagCode.USER_NOT_FOUND])

        if user.status in {"suspended", "blocked"}:
            return EligibilityResult(False, "User account is blocked", [FlagCode.USER_BLOCKED])

        kyc_stmt = (
            select(UserKycVerification)
            .where(UserKycVerification.user_id == user.id)
            .order_by(UserKycVerification.created_at.desc())
        )
        latest_kyc = (await db.execute(kyc_stmt)).scalars().first()
        if not latest_kyc or latest_kyc.status != KycStatus.APPROVED:
            return EligibilityResult(False, "KYC must be approved before credit assessment", [FlagCode.KYC_NOT_APPROVED])

        return EligibilityResult(True, None, [FlagCode.HARD_BLOCKS_CLEAR])
