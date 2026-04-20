from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.checkout import PurchaseExecution


class ExecutionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_uuid(self, execution_uuid):
        return await self.db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == execution_uuid))

    async def find_active(self, order_id: int, vcn_id: int) -> PurchaseExecution | None:
        return await self.db.scalar(
            select(PurchaseExecution)
            .where(
                PurchaseExecution.order_id == order_id,
                PurchaseExecution.vcn_id == vcn_id,
                PurchaseExecution.status.in_(["queued", "running", "pending_verification"]),
            )
            .order_by(desc(PurchaseExecution.created_at))
        )
    async def find_by_order_id(self, order_id: int) -> list[PurchaseExecution]:
        rows = await self.db.scalars(
            select(PurchaseExecution).where(PurchaseExecution.order_id == order_id).order_by(desc(PurchaseExecution.created_at))
        )
        return list(rows)

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[PurchaseExecution]:
        rows = await self.db.scalars(
            select(PurchaseExecution).order_by(desc(PurchaseExecution.created_at)).limit(limit).offset(offset)
        )
        return list(rows)
