from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import JournalEntry, JournalEntryLine, LedgerAccount, LedgerAccountBalance
from src.core.readonly_guard import readonly_guard

logger = logging.getLogger(__name__)


class BalanceService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    @readonly_guard
    async def get_account_balance(self, account_code: str, as_of: date | None = None) -> dict[str, object]:
        """
        Get the balance of an account as of a specific date.
        Uses snapshots if available for performance.
        """
        target_date = as_of or date.today()
        
        # 1. Try to find the latest snapshot at or before target_date
        snapshot_stmt = (
            select(LedgerAccountBalance)
            .join(LedgerAccount, LedgerAccount.id == LedgerAccountBalance.account_id)
            .where(LedgerAccount.account_code == account_code)
            .where(LedgerAccountBalance.snapshot_date <= target_date)
            .order_by(LedgerAccountBalance.snapshot_date.desc())
            .limit(1)
        )
        snapshot = (await self.db.execute(snapshot_stmt)).scalar_one_or_none()
        
        start_date = None
        current_debit = Decimal("0.00")
        current_credit = Decimal("0.00")
        
        if snapshot:
            start_date = snapshot.snapshot_date
            current_debit = snapshot.debit_balance
            current_credit = snapshot.credit_balance
            # If snapshot is exactly at target_date, we are done
            if start_date == target_date:
                return await self._format_balance(account_code, target_date, current_debit, current_credit)

        # 2. Aggregate entries from start_date + 1 day to target_date
        entries_stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .join(LedgerAccount, LedgerAccount.id == JournalEntryLine.account_id)
            .where(LedgerAccount.account_code == account_code)
            .where(JournalEntry.entry_date <= target_date)
        )
        if start_date:
            entries_stmt = entries_stmt.where(JournalEntry.entry_date > start_date)
        
        delta_debit, delta_credit = (await self.db.execute(entries_stmt)).one()
        
        current_debit += Decimal(str(delta_debit))
        current_credit += Decimal(str(delta_credit))
        
        return await self._format_balance(account_code, target_date, current_debit, current_credit)

    async def create_snapshot(self, account_code: str, snapshot_date: date) -> LedgerAccountBalance:
        """
        Create a balance snapshot for an account as of a specific date.
        """
        balance_data = await self.get_account_balance(account_code, as_of=snapshot_date)
        
        account_stmt = select(LedgerAccount).where(LedgerAccount.account_code == account_code)
        account = (await self.db.execute(account_stmt)).scalar_one()
        
        # Check if snapshot already exists
        existing_stmt = select(LedgerAccountBalance).where(
            LedgerAccountBalance.account_id == account.id,
            LedgerAccountBalance.snapshot_date == snapshot_date
        )
        snapshot = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        
        if snapshot:
            snapshot.debit_balance = Decimal(str(balance_data["debit_total"]))
            snapshot.credit_balance = Decimal(str(balance_data["credit_total"]))
            snapshot.net_balance = Decimal(str(balance_data["balance"]))
        else:
            snapshot = LedgerAccountBalance(
                account_id=account.id,
                snapshot_date=snapshot_date,
                debit_balance=Decimal(str(balance_data["debit_total"])),
                credit_balance=Decimal(str(balance_data["credit_total"])),
                net_balance=Decimal(str(balance_data["balance"])),
            )
            self.db.add(snapshot)
            
        await self.db.flush()
        return snapshot

    async def _format_balance(self, account_code: str, as_of: date, debit: Decimal, credit: Decimal) -> dict[str, object]:
        account_stmt = select(LedgerAccount).where(LedgerAccount.account_code == account_code)
        account = (await self.db.execute(account_stmt)).scalar_one()
        
        if account.normal_balance == "debit":
            balance = debit - credit
        else:
            balance = credit - debit
            
        return {
            "account_code": account_code,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "normal_balance": account.normal_balance,
            "as_of": as_of.isoformat(),
            "debit_total": float(debit),
            "credit_total": float(credit),
            "balance": float(balance),
        }
