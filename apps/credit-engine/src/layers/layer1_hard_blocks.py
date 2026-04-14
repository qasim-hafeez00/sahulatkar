from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS
from sk_shared.models.auth import User
from sk_shared.models.credit import BlacklistedEntity
from sk_shared.models.kyc import KycStatus, UserKycVerification
from sk_shared.redis_client import RedisClient


PROHIBITED_CATEGORIES = {
    "alcohol",
    "tobacco",
    "gambling",
    "adult content",
    "weapons",
    "interest-bearing instruments",
    "non-halal food",
}


async def run_hard_blocks(
    db: AsyncSession,
    redis_client: RedisClient,
    user_uuid: str,
    product_category: str | None = None,
) -> tuple[bool, Optional[str], list[str]]:
    flags: list[str] = []

    if product_category and product_category.strip().lower() in PROHIBITED_CATEGORIES:
        return True, "Prohibited product category", ["prohibited_category"]

    blacklist_key = f"{RedisNS.CREDIT_BLACKLIST}:user:{user_uuid}"
    cached_blacklist = await redis_client.get(blacklist_key)
    if cached_blacklist:
        return True, "User is blacklisted", ["blacklist_cache_hit"]

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
            return True, "User is blacklisted", ["blacklist_db_hit"]

    try:
        user_uuid_obj = UUID(user_uuid)
    except ValueError:
        return True, "Invalid user id", ["invalid_user_id"]

    user_stmt = select(User).where(User.uuid == user_uuid_obj, User.deleted_at == None)  # noqa: E711
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        return True, "User not found", ["user_not_found"]

    if user.status in {"suspended", "blocked"}:
        return True, "User account is blocked", ["user_blocked"]

    kyc_stmt = (
        select(UserKycVerification)
        .where(UserKycVerification.user_id == user.id)
        .order_by(UserKycVerification.created_at.desc())
    )
    latest_kyc = (await db.execute(kyc_stmt)).scalars().first()
    if not latest_kyc or latest_kyc.status != KycStatus.APPROVED:
        return True, "KYC must be approved before credit assessment", ["kyc_not_approved"]

    flags.append("hard_blocks_clear")
    return False, None, flags
