from datetime import datetime, timezone
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sk_shared.constants import QueueName
from sk_shared.models.auth import User
from sk_shared.models.kyc import KycStatus, KycVerificationQueue, UserKycVerification
from sk_shared.redis_client import RedisClient


class KycQueueService:
    def __init__(self, db: AsyncSession, redis: RedisClient | None = None):
        self.db = db
        self.redis = redis

    async def get_queue(self) -> list[KycVerificationQueue]:
        result = await self.db.execute(
            select(KycVerificationQueue).where(
                KycVerificationQueue.assigned_admin_id == None  # noqa: E711
            )
        )
        return result.scalars().all()

    async def claim(self, queue_id: int, admin_id: int) -> KycVerificationQueue:
        result = await self.db.execute(
            select(KycVerificationQueue).where(KycVerificationQueue.id == queue_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise ValueError(f"Queue entry {queue_id} not found.")

        entry.assigned_admin_id = admin_id
        entry.claimed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def process_decision(
        self,
        queue_id: int,
        admin_id: int,
        approved: bool,
        reason: str | None = None,
    ) -> UserKycVerification:
        result = await self.db.execute(
            select(KycVerificationQueue).where(KycVerificationQueue.id == queue_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise ValueError(f"Queue entry {queue_id} not found.")

        result = await self.db.execute(
            select(UserKycVerification).where(
                UserKycVerification.id == entry.kyc_verification_id
            )
        )
        kyc = result.scalar_one()

        if approved:
            kyc.status = KycStatus.APPROVED
            user = (
                await self.db.execute(select(User).where(User.id == kyc.user_id, User.deleted_at == None))  # noqa: E711
            ).scalar_one_or_none()

            if self.redis and user:
                job = {
                    "event": "kyc.approved",
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "user_id": str(user.uuid),
                    "kyc_verification_id": kyc.id,
                }
                if hasattr(self.redis, "redis"):
                    await self.redis.redis.lpush(QueueName.CREDIT_ASSESS, json.dumps(job))
        else:
            kyc.status = KycStatus.REJECTED
            kyc.rejection_reason = reason or "Rejected by admin."

        await self.db.delete(entry)
        await self.db.commit()
        await self.db.refresh(kyc)
        return kyc
