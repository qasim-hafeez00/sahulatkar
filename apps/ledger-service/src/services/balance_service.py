from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Iterable

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

    @readonly_guard
    async def get_account_balances_batch(
        self,
        account_codes: Iterable[str] | None,
        as_of: date | None = None,
        currency: str | None = None,
    ) -> dict[str, dict[str, object]]:
        """
        Batched equivalent of calling get_account_balance() once per account.

        Fixes an N+1 query pattern: get_trial_balance() and list_accounts()
        used to call get_account_balance() in a per-account loop, which for
        every account issued a lookup-by-code query plus (for leaf accounts)
        a snapshot query and an aggregate query -- O(N) queries for N
        accounts. This method instead issues a small, constant number of
        queries (chart of accounts, snapshots, journal-entry-line deltas)
        regardless of how many accounts are requested, then resolves
        per-account (and, for control accounts, rolled-up) balances in
        Python from that already-fetched data.

        Args:
            account_codes: account codes to return balances for. If None,
                balances are returned for every account in the chart.
            as_of: date to compute balances as of (defaults to today).
            currency: pin all accounts to this currency instead of each
                account's own default currency.

        Returns:
            Dict keyed by account_code, with the same shape as
            get_account_balance()'s return value.
        """
        target_date = as_of or date.today()

        # Fetch the full chart of accounts once. This is required (not just
        # an optimization) because control-account rollups need their full
        # descendant subtree, which may include accounts outside the
        # requested `account_codes` set. The chart of accounts is small
        # (dozens of rows), so this single extra query is cheap relative to
        # the N+1 pattern it replaces.
        all_accounts = (await self.db.execute(select(LedgerAccount))).scalars().all()
        accounts_by_id = {account.id: account for account in all_accounts}
        accounts_by_code = {account.account_code: account for account in all_accounts}

        children_by_parent: dict[int, list[LedgerAccount]] = {}
        for account in all_accounts:
            if account.parent_account_id is not None:
                children_by_parent.setdefault(account.parent_account_id, []).append(account)

        leaf_ids = [account.id for account in all_accounts if not account.is_control]
        leaf_balances = await self._get_single_account_balances_bulk(
            leaf_ids, target_date, currency, accounts_by_id
        )

        resolved: dict[int, dict[str, Decimal]] = {}

        def _resolve(account: LedgerAccount) -> dict[str, Decimal]:
            if account.id in resolved:
                return resolved[account.id]

            if not account.is_control:
                target_currency = currency or account.currency
                data = leaf_balances.get(
                    (account.id, target_currency),
                    {"debit_total": Decimal("0.00"), "credit_total": Decimal("0.00"), "balance": Decimal("0.00")},
                )
            else:
                total_debit = Decimal("0.00")
                total_credit = Decimal("0.00")
                total_balance = Decimal("0.00")
                for child in children_by_parent.get(account.id, []):
                    child_data = _resolve(child)
                    total_debit += child_data["debit_total"]
                    total_credit += child_data["credit_total"]
                    total_balance += child_data["balance"]
                data = {"debit_total": total_debit, "credit_total": total_credit, "balance": total_balance}

            resolved[account.id] = data
            return data

        codes = list(account_codes) if account_codes is not None else list(accounts_by_code)
        results: dict[str, dict[str, object]] = {}
        for code in codes:
            account = accounts_by_code.get(code)
            if account is None:
                continue
            data = _resolve(account)
            target_currency = currency or account.currency
            results[code] = {
                "account_code": account.account_code,
                "account_name": account.account_name,
                "account_type": account.account_type,
                "normal_balance": account.normal_balance,
                "is_control": bool(account.is_control),
                "currency": target_currency,
                "as_of": target_date.isoformat(),
                "debit_total": float(data["debit_total"]),
                "credit_total": float(data["credit_total"]),
                "balance": float(data["balance"]),
            }
        return results

    async def _get_single_account_balances_bulk(
        self,
        account_ids: list[int],
        target_date: date,
        currency: str | None,
        accounts_by_id: dict[int, LedgerAccount],
    ) -> dict[tuple[int, str], dict[str, Decimal]]:
        """
        Batched equivalent of _get_single_account_balance() for many accounts
        at once: two queries total (latest-snapshot lookup + journal-entry-line
        delta aggregation) instead of two queries PER account.
        """
        if not account_ids:
            return {}

        # 1. Latest snapshot at or before target_date, per (account_id, currency).
        # Ordering by account_id then snapshot_date desc means the first row
        # seen for each (account_id, currency) pair is the latest snapshot --
        # avoids needing a window function (portable to sqlite in tests).
        snapshot_stmt = (
            select(LedgerAccountBalance)
            .where(LedgerAccountBalance.account_id.in_(account_ids))
            .where(LedgerAccountBalance.snapshot_date <= target_date)
            .order_by(LedgerAccountBalance.account_id.asc(), LedgerAccountBalance.snapshot_date.desc())
        )
        snapshot_rows = (await self.db.execute(snapshot_stmt)).scalars().all()

        snapshots: dict[tuple[int, str], LedgerAccountBalance] = {}
        for row in snapshot_rows:
            key = (row.account_id, row.currency)
            if key not in snapshots:
                snapshots[key] = row

        # 2. All journal entry line deltas for these accounts up to target_date,
        # in one query -- filtered per-account against that account's own
        # snapshot start-date (if any) in Python below, matching
        # _get_single_account_balance()'s "entries after the snapshot date"
        # semantics without needing a correlated per-account query.
        entries_stmt = (
            select(
                JournalEntryLine.account_id,
                JournalEntryLine.currency,
                JournalEntry.entry_date,
                JournalEntryLine.debit_amount,
                JournalEntryLine.credit_amount,
            )
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_id)
            .where(JournalEntryLine.account_id.in_(account_ids))
            .where(JournalEntry.entry_date <= target_date)
        )
        entry_rows = (await self.db.execute(entries_stmt)).all()

        deltas: dict[tuple[int, str], list[Decimal]] = {}
        for row in entry_rows:
            key = (row.account_id, row.currency)
            snapshot = snapshots.get(key)
            if snapshot is not None and row.entry_date <= snapshot.snapshot_date:
                continue
            bucket = deltas.setdefault(key, [Decimal("0.00"), Decimal("0.00")])
            bucket[0] += Decimal(str(row.debit_amount))
            bucket[1] += Decimal(str(row.credit_amount))

        results: dict[tuple[int, str], dict[str, Decimal]] = {}
        for account_id in account_ids:
            account = accounts_by_id[account_id]
            target_currency = currency or account.currency
            key = (account_id, target_currency)

            snapshot = snapshots.get(key)
            current_debit = snapshot.debit_balance if snapshot else Decimal("0.00")
            current_credit = snapshot.credit_balance if snapshot else Decimal("0.00")

            delta_debit, delta_credit = deltas.get(key, [Decimal("0.00"), Decimal("0.00")])
            total_debit = current_debit + delta_debit
            total_credit = current_credit + delta_credit

            if account.normal_balance == "debit":
                balance = total_debit - total_credit
            else:
                balance = total_credit - total_debit

            results[key] = {"debit_total": total_debit, "credit_total": total_credit, "balance": balance}

        return results

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
