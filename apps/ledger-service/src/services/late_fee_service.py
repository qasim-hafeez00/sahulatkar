from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.payment import Installment
from src.services.accounting_service import AccountingService


class LateFeeService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def apply_late_fee_to_installment(self, installment_id: int, amount: Decimal | float | int) -> dict[str, object]:
        installment = await self._get_installment(installment_id)
        if installment.late_fee_waived:
            return {"status": "waived", "amount": 0.0, "installment_id": installment_id}

        fee_amount = Decimal(str(amount))
        if fee_amount <= Decimal("0"):
            return {"status": "not_applicable", "amount": 0.0, "installment_id": installment_id}

        if Decimal(str(installment.late_fee_amount or 0)) > Decimal("0"):
            return {
                "status": "already_applied",
                "amount": float(Decimal(str(installment.late_fee_amount))),
                "installment_id": installment_id,
            }

        accounting = AccountingService(self.db)
        await accounting.record_late_fee(installment_id=installment_id, amount=fee_amount)
        installment.late_fee_amount = fee_amount
        await self.db.commit()
        return {"status": "applied", "amount": float(fee_amount), "installment_id": installment_id}

    async def waive_late_fee(self, installment_id: int, reason: str | None = None) -> dict[str, object]:
        installment = await self._get_installment(installment_id)
        installment.late_fee_waived = True
        await self.db.commit()
        return {
            "status": "waived",
            "installment_id": installment_id,
            "reason": reason,
            "waived_amount": float(Decimal(str(installment.late_fee_amount or 0))),
        }

    async def get_late_fee_summary(self, user_id: int) -> dict[str, object]:
        rows = (
            await self.db.execute(
                select(Installment.late_fee_amount, Installment.late_fee_waived)
                .where(Installment.user_id == user_id, Installment.deleted_at.is_(None))
            )
        ).all()
        charged = sum((Decimal(str(row.late_fee_amount or 0)) for row in rows), Decimal("0.00"))
        waived = sum((Decimal(str(row.late_fee_amount or 0)) for row in rows if row.late_fee_waived), Decimal("0.00"))
        outstanding = charged - waived
        return {
            "user_id": user_id,
            "total_charged": float(charged),
            "total_waived": float(waived),
            "outstanding": float(outstanding),
            "installment_count": len(rows),
        }

    async def _get_installment(self, installment_id: int) -> Installment:
        installment = (
            await self.db.execute(
                select(Installment).where(Installment.id == installment_id, Installment.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if installment is None:
            raise LookupError(f"Installment {installment_id} not found")
        return installment
