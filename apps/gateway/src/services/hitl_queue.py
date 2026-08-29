from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.hitl import HitlQueue


class HitlQueueService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_queue(self, *, status: str | None = None) -> list[HitlQueue]:
        statement = select(HitlQueue)
        if status:
            statement = statement.where(HitlQueue.status == status)
        statement = statement.order_by(HitlQueue.priority.asc(), HitlQueue.created_at.asc())
        result = await self.db.execute(statement)
        return result.scalars().all()

    async def get_item(self, queue_id: int) -> HitlQueue | None:
        return await self._load_item(queue_id)

    async def claim(self, queue_id: int, admin_id: int) -> HitlQueue:
        item = await self._load_item(queue_id)
        if item is None:
            raise ValueError("HITL_ITEM_NOT_FOUND")
        if item.status != "pending":
            raise ValueError("HITL_ITEM_NOT_PENDING")

        item.assigned_to = admin_id
        item.status = "claimed"
        item.claimed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def start(self, queue_id: int, admin_id: int) -> HitlQueue:
        item = await self._load_item(queue_id)
        if item is None:
            raise ValueError("HITL_ITEM_NOT_FOUND")
        if item.assigned_to != admin_id:
            raise ValueError("HITL_ITEM_NOT_ASSIGNED_TO_ADMIN")
        if item.status not in {"claimed", "in_progress"}:
            raise ValueError("HITL_ITEM_NOT_CLAIMED")

        item.status = "in_progress"
        if item.in_progress_at is None:
            item.in_progress_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def resolve(self, queue_id: int, admin_id: int, resolution: str) -> HitlQueue:
        item = await self._load_item(queue_id)
        if item is None:
            raise ValueError("HITL_ITEM_NOT_FOUND")
        if item.assigned_to != admin_id:
            raise ValueError("HITL_ITEM_NOT_ASSIGNED_TO_ADMIN")
        if item.status not in {"claimed", "in_progress"}:
            raise ValueError("HITL_ITEM_NOT_ACTIVE")

        item.status = "resolved"
        item.resolution = resolution
        item.resolved_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def cancel(self, queue_id: int, admin_id: int) -> HitlQueue:
        item = await self._load_item(queue_id)
        if item is None:
            raise ValueError("HITL_ITEM_NOT_FOUND")
        if item.assigned_to not in {None, admin_id}:
            raise ValueError("HITL_ITEM_ASSIGNED_TO_OTHER_ADMIN")
        if item.status in {"resolved", "cancelled"}:
            raise ValueError("HITL_ITEM_ALREADY_FINAL")

        item.assigned_to = admin_id
        item.status = "cancelled"
        item.resolved_at = datetime.utcnow()
        item.resolution = "cancelled"
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def _load_item(self, queue_id: int) -> HitlQueue | None:
        return await self.db.scalar(select(HitlQueue).where(HitlQueue.id == queue_id))