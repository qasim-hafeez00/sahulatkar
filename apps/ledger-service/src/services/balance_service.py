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
    async def get_account_balance(
        self, 
        account_code: str, 
        as_of: date | None = None,
        currency: str | None = None
    ) -> dict[str, object]:
        """
        Get the balance of an account as of a specific date.
        P1-01: Supports hierarchical rollups for control accounts and currency filtering.
        """
        target_date = as_of or date.today()
        
        stmt = select(LedgerAccount).where(LedgerAccount.account_code == account_code)
        account = (await self.db.execute(stmt)).scalar_one_or_none()
        if account is None:
            raise LookupError("ACCOUNT_NOT_FOUND")

        # Resolve effective currency (default to account currency if not specified)
        target_currency = currency or account.currency

        if account.is_control:
            # Hierarchical rollup
            balance_data = await self._get_rolled_up_balance(account.id, target_date, target_currency)
        else:
            # Single account balance (optimized with snapshots)
            balance_data = await self._get_single_account_balance(account.id, target_date, target_currency)

        return {
            "account_code": account.account_code,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "normal_balance": account.normal_balance,
            "is_control": bool(account.is_control),
            "currency": target_currency,
            "as_of": target_date.isoformat(),
            "debit_total": float(balance_data["debit_total"]),
            "credit_total": float(balance_data["credit_total"]),
            "balance": float(balance_data["balance"]),
        }

    async def _get_single_account_balance(self, account_id: int, target_date: date, currency: str) -> dict[str, Decimal]:
        """Calculates balance for a single account using snapshots and incremental aggregation."""
        # 1. Try to find the latest snapshot at or before target_date
        snapshot_stmt = (
            select(LedgerAccountBalance)
            .where(LedgerAccountBalance.account_id == account_id)
            .where(LedgerAccountBalance.snapshot_date <= target_date)
            .where(LedgerAccountBalance.currency == currency)
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
            if start_date == target_date:
                return await self._calculate_balance_for_account(account_id, current_debit, current_credit)

        # 2. Aggregate entries from start_date + 1 day to target_date
        entries_stmt = (
            select(
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(JournalEntryLine.account_id == account_id)
            .where(JournalEntryLine.currency == currency)
            .where(JournalEntry.entry_date <= target_date)
        )
        if start_date:
            entries_stmt = entries_stmt.where(JournalEntry.entry_date > start_date)
        
        delta_debit, delta_credit = (await self.db.execute(entries_stmt)).one()
        
        total_debit = current_debit + Decimal(str(delta_debit))
        total_credit = current_credit + Decimal(str(delta_credit))
        
        return await self._calculate_balance_for_account(account_id, total_debit, total_credit)

    async def _get_rolled_up_balance(self, parent_id: int, target_date: date, currency: str) -> dict[str, Decimal]:
        """Recursively rolls up balances from children."""
        children_stmt = select(LedgerAccount).where(LedgerAccount.parent_account_id == parent_id)
        children = (await self.db.execute(children_stmt)).scalars().all()
        
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        total_balance = Decimal("0.00")
        
        for child in children:
            if child.is_control:
                child_data = await self._get_rolled_up_balance(child.id, target_date, currency)
            else:
                child_data = await self._get_single_account_balance(child.id, target_date, currency)
            
            total_debit += child_data["debit_total"]
            total_credit += child_data["credit_total"]
            total_balance += child_data["balance"]
            
        return {"debit_total": total_debit, "credit_total": total_credit, "balance": total_balance}

    async def _calculate_balance_for_account(self, account_id: int, debit: Decimal, credit: Decimal) -> dict[str, Decimal]:
        acc_stmt = select(LedgerAccount.normal_balance).where(LedgerAccount.id == account_id)
        normal_balance = (await self.db.execute(acc_stmt)).scalar_one()
        
        if normal_balance == "debit":
            balance = debit - credit
        else:
            balance = credit - debit
        return {"debit_total": debit, "credit_total": credit, "balance": balance}

    async def create_snapshot(self, account_code: str, snapshot_date: date, currency: str | None = None) -> LedgerAccountBalance:
        """
        Create a balance snapshot for an account as of a specific date.
        """
        stmt = select(LedgerAccount).where(LedgerAccount.account_code == account_code)
        account = (await self.db.execute(stmt)).scalar_one()
        target_currency = currency or account.currency

        balance_data = await self.get_account_balance(account_code, as_of=snapshot_date, currency=target_currency)
        
        # Check if snapshot already exists
        existing_stmt = select(LedgerAccountBalance).where(
            LedgerAccountBalance.account_id == account.id,
            LedgerAccountBalance.snapshot_date == snapshot_date,
            LedgerAccountBalance.currency == target_currency
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
                currency=target_currency,
                debit_balance=Decimal(str(balance_data["debit_total"])),
                credit_balance=Decimal(str(balance_data["credit_total"])),
                net_balance=Decimal(str(balance_data["balance"])),
            )
            self.db.add(snapshot)
            
        await self.db.flush()
        return snapshot
