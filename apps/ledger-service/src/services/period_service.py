from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import LedgerPeriod
from src.core.period_utils import get_period_bounds, get_period_key
from src.domain.period_rules import PeriodStatus, assert_period_open

logger = logging.getLogger(__name__)


class PeriodService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def get_or_create_period(self, period_key: str) -> LedgerPeriod:
        """Get an existing period or create it if it doesn't exist."""
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == period_key)
        period = (await self.db.execute(stmt)).scalar_one_or_none()
        
        if not period:
            start_date, end_date = get_period_bounds(period_key)
            try:
                fiscal_year = int(period_key.split("-")[0])
            except (ValueError, IndexError):
                fiscal_year = start_date.year

            period = LedgerPeriod(
                period_key=period_key,
                fiscal_year=fiscal_year,
                start_date=start_date,
                end_date=end_date,
                status=PeriodStatus.OPEN
            )
            self.db.add(period)
            await self.db.flush()
            
        return period

    async def ensure_period_open(self, target_date: date) -> str:
        """
        Ensure the period for a given date is open.
        Returns the period_key.
        """
        period_key = get_period_key(target_date)
        period = await self.get_or_create_period(period_key)
        assert_period_open(period.status)
        return period_key

    async def close_period(self, period_key: str, closed_by: str) -> LedgerPeriod:
        """Close an accounting period and generate closing entries if end-of-year."""
        period = await self.get_or_create_period(period_key)
        if period.status == PeriodStatus.CLOSED:
            raise ValueError(f"Period {period_key} is already closed")
            
        period.status = PeriodStatus.CLOSED
        period.closed_at = datetime.now(timezone.utc)
        period.closed_by = closed_by
        
        # P2-08: If this is the last period of the year, zero out temporary accounts
        if period_key.endswith("-12"):
            from src.services.accounting_service import AccountingService
            from src.accounting.accounts import ACCOUNT_CODES
            from sk_shared.models.ledger import PostingLine
            from decimal import Decimal

            accounting = AccountingService(self.db)
            # Fetch P&L report for the full year to know how much to close out
            pl = await accounting.build_profit_loss_report(period_key)
            
            # For a proper close, we should ideally fetch balances of all individual revenue/expense accounts
            # and zero them out line by line. Here we aggregate to Retained Earnings based on Net Income.
            # Revenue accounts have credit balances (debit to close)
            # Expense accounts have debit balances (credit to close)
            net_income = Decimal(str(pl["net_income"]))
            revenue = Decimal(str(pl["revenue"]))
            expenses = Decimal(str(pl["costs"]))
            
            if revenue > 0 or expenses > 0:
                lines = []
                # To balance the entry perfectly without individual account breakdown, 
                # we just do a summary entry if net_income is non-zero. 
                # Actually, a real closing entry requires closing EACH temp account.
                revenue_accounts = {ACCOUNT_CODES["murabaha_profit"], ACCOUNT_CODES["affiliate_commission"], ACCOUNT_CODES["late_fee_collections"]}
                expense_accounts = {ACCOUNT_CODES["cogs_merchant_payment"], ACCOUNT_CODES["gateway_fees"], ACCOUNT_CODES["vcn_issuance"], ACCOUNT_CODES["loan_loss_provision"]}
                
                for acct in revenue_accounts:
                    bal = await accounting.get_account_balance(acct, target_date=period.end_date)
                    b = Decimal(str(bal["balance"]))
                    if b > 0:
                        lines.append(PostingLine(acct, debit_amount=b))
                
                for acct in expense_accounts:
                    bal = await accounting.get_account_balance(acct, target_date=period.end_date)
                    b = Decimal(str(bal["balance"]))
                    if b > 0:
                        lines.append(PostingLine(acct, credit_amount=b))
                        
                # The balancing figure goes to retained earnings
                total_dr = sum(l.debit_amount for l in lines)
                total_cr = sum(l.credit_amount for l in lines)
                retained = total_dr - total_cr
                
                if retained > 0:
                    lines.append(PostingLine(ACCOUNT_CODES["retained_earnings"], credit_amount=retained))
                elif retained < 0:
                    lines.append(PostingLine(ACCOUNT_CODES["retained_earnings"], debit_amount=abs(retained)))

                if lines:
                    await accounting.record_manual_entry(
                        entry_type="closing_entry",
                        source_type="period_close",
                        source_id=period.fiscal_year,
                        lines=lines,
                        description=f"Annual closing entry for fiscal year {period.fiscal_year}",
                        target_date=period.end_date,
                    )

        await self.db.flush()
        return period

    async def reopen_period(self, period_key: str) -> LedgerPeriod:
        """Reopen a closed period."""
        period = await self.get_or_create_period(period_key)
        if period.status == PeriodStatus.OPEN:
            return period
            
        period.status = PeriodStatus.OPEN
        period.closed_at = None
        period.closed_by = None
        
        await self.db.flush()
        return period

    async def seed_fiscal_year(self, year: int) -> list[LedgerPeriod]:
        """
        P3-03: Implement fiscal year seeding.
        Creates all 12 monthly periods for a given fiscal year.
        """
        periods = []
        for month in range(1, 13):
            period_key = f"{year}-{month:02d}"
            period = await self.get_or_create_period(period_key)
            # Ensure fiscal_year field is set (GAP-05)
            period.fiscal_year = year
            periods.append(period)
        
        await self.db.flush()
        return periods

    async def list_periods(self, limit: int = 12) -> list[LedgerPeriod]:
        """List periods ordered by date descending."""
        stmt = select(LedgerPeriod).order_by(LedgerPeriod.start_date.desc()).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())
