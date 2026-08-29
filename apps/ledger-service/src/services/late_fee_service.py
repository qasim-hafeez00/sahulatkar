from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import JournalEntry
from sk_shared.models.payment import Installment, Loan
from sk_shared.redis_client import RedisClient
from src.events.publisher import EventPublisher
from src.services.accounting_service import AccountingService


class LateFeeService:
    def __init__(self, db_session: AsyncSession, redis: RedisClient | None = None) -> None:
        self.db = db_session
        self.publisher = EventPublisher(redis) if redis else None

    async def apply_late_fee_to_installment(self, installment_id: int, amount: Decimal | float | int) -> dict[str, object]:
        installment = await self._get_installment(installment_id)
        if installment.late_fee_waived:
            return {"status": "waived", "amount": 0.0, "installment_id": installment_id}

        fee_amount = Decimal(str(amount))
        if fee_amount <= Decimal("0"):
            return {"status": "not_applicable", "amount": 0.0, "installment_id": installment_id}

        # LS-CRIT-XX: `installment.late_fee_amount` is never written back by any
        # consumer (Ledger deliberately doesn't write to the shared `installments`
        # table -- it only publishes `late_fee_applied`, and nothing subscribes to
        # write the field), so that column can never be used as an idempotency
        # signal. Instead, check for a late-fee JournalEntry Ledger itself already
        # posted for this installment -- the same source_type/source_id pair
        # record_late_fee() uses for its own idempotency check. A late fee is
        # applied once per overdue episode (in this schema, an installment has at
        # most one overdue episode over its lifetime -- it never cycles back to
        # `pending` after being charged), matching the one-row-per-installment
        # UniqueConstraint on LateFeeCharityAllocation.installment_id.
        existing_entry = await self._find_existing_late_fee_entry(installment_id)
        if existing_entry is not None:
            return {
                "status": "already_applied",
                "amount": float(Decimal(str(existing_entry.total_debit))),
                "installment_id": installment_id,
            }

        # LS-BL-08: Shariah compliance — late fee cannot exceed principal of the loan.
        loan = await self._get_loan(installment.loan_id)
        principal = Decimal(str(loan.principal_amount))
        if fee_amount > principal:
            raise ValueError(
                f"LATE_FEE_EXCEEDS_PRINCIPAL: late_fee={fee_amount} > principal={principal} "
                f"for installment {installment_id}. Islamic finance forbids this."
            )

        accounting = AccountingService(self.db)
        await accounting.record_late_fee(installment_id=installment_id, amount=fee_amount)
        
        # BV-04: We no longer update the installments table directly.
        # Instead, we publish an event.
        if self.publisher:
            await self.publisher.publish_late_fee_applied(installment_id, float(fee_amount))

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

    async def _find_existing_late_fee_entry(self, installment_id: int) -> JournalEntry | None:
        """Mirrors AccountingService._create_balanced_entry's own idempotency
        lookup (source_type/source_id) so both layers agree on whether a late
        fee was already applied for this installment."""
        return (
            await self.db.execute(
                select(JournalEntry).where(
                    JournalEntry.source_type == "installment.late_fee",
                    JournalEntry.source_id == installment_id,
                )
            )
        ).scalar_one_or_none()

    async def _get_installment(self, installment_id: int) -> Installment:
        installment = (
            await self.db.execute(
                select(Installment).where(Installment.id == installment_id, Installment.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if installment is None:
            raise LookupError(f"Installment {installment_id} not found")
        return installment

    async def _get_loan(self, loan_id: int) -> Loan:
        loan = (
            await self.db.execute(
                select(Loan).where(Loan.id == loan_id, Loan.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if loan is None:
            raise LookupError(f"Loan {loan_id} not found for Shariah principal cap check")
        return loan
