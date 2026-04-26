from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.notification import NotificationDispatch, DispatchStatus

class RetryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_due_retries(self, limit: int = 100) -> list[NotificationDispatch]:
        query = select(NotificationDispatch).where(
            NotificationDispatch.status == DispatchStatus.RETRYING,
            NotificationDispatch.next_retry_at <= datetime.now(timezone.utc)
        ).limit(limit)
        
        return list((await self.db.scalars(query)).all())
