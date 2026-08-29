from __future__ import annotations

import logging
from datetime import date, datetime

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
        Raises ValueError if the period is CLOSED (LS-BL-02: no backdated entries into closed periods).
        """
        period_key = get_period_key(target_date)
        period = await self.get_or_create_period(period_key)
        if period.status == PeriodStatus.CLOSED:
            raise ValueError(
                f"PERIOD_CLOSED_BACKDATED_ENTRY_REJECTED: Period {period_key} is closed. "
                "Entries cannot be posted into a closed accounting period."
            )
        assert_period_open(period.status)
        return period_key

    async def close_period(self, period_key: str, closed_by: str) -> LedgerPeriod:
        """Close an accounting period and generate closing entries if end-of-year."""
        period = await self.get_or_create_period(period_key)
        if period.status == PeriodStatus.CLOSED:
            raise ValueError(f"Period {period_key} is already closed")

        # P2-08: If this is the last period of the year, zero out temporary accounts.
        # This MUST run while the period is still OPEN — record_manual_entry posts
        # the closing entry dated period.end_date, and ensure_period_open() would
        # reject that as a backdated entry into a closed period otherwise.
        if period_key.endswith("-12"):
            from src.services.accounting_service import AccountingService
            from src.accounting.accounts import ACCOUNT_CODES
            from src.domain.posting_engine import PostingLine
            from decimal import Decimal

            accounting = AccountingService(self.db)
            # Fetch P&L report for the full year to know how much to close out
            pl = await accounting.build_profit_loss_report(period_key)

            # For a proper close, we should ideally fetch balances of all individual revenue/expense accounts
            # and zero them out line by line. Here we aggregate to Retained Earnings based on Net Income.
            # Revenue accounts have credit balances (debit to close)
            # Expense accounts have debit balances (credit to close)
            Decimal(str(pl["net_income"]))
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
                    bal = await accounting.get_account_balance(acct, as_of=period.end_date.isoformat())
                    b = Decimal(str(bal["balance"]))
                    if b > 0:
                        lines.append(PostingLine(acct, debit_amount=b))

                for acct in expense_accounts:
                    bal = await accounting.get_account_balance(acct, as_of=period.end_date.isoformat())
                    b = Decimal(str(bal["balance"]))
                    if b > 0:
                        lines.append(PostingLine(acct, credit_amount=b))

                # The balancing figure goes to retained earnings
                total_dr = sum(ln.debit_amount for ln in lines)
                total_cr = sum(ln.credit_amount for ln in lines)
                retained = total_dr - total_cr

                if retained > 0:
                    lines.append(PostingLine(ACCOUNT_CODES["retained_earnings"], credit_amount=retained))
                elif retained < 0:
                    lines.append(PostingLine(ACCOUNT_CODES["retained_earnings"], debit_amount=abs(retained)))

                if lines:
                    await accounting.record_manual_entry(
                        lines=[
                            {
                                "account_code": line.account_code,
                                "debit_amount": line.debit_amount,
                                "credit_amount": line.credit_amount,
                            }
                            for line in lines
                        ],
                        description=f"Annual closing entry for fiscal year {period.fiscal_year}",
                        entry_date=period.end_date,
                        reference=f"period-close-{period_key}",
                    )

        period.status = PeriodStatus.CLOSED
        period.closed_at = datetime.utcnow()
        period.closed_by = closed_by

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

    async def get_upcoming_period_closes(self, within_days: int = 7) -> list[dict[str, object]]:
        """
        LS-BL-07: Return open periods whose end_date is within `within_days` days from today.
        Used for alerting admins that a period is near its close date.
        """
        today = date.today()
        date(today.year + (today.month // 12), (today.month % 12) + 1, 1)
        # Simple approach: list open periods whose end_date <= today + within_days
        from datetime import timedelta
        warning_threshold = today + timedelta(days=within_days)
        stmt = (
            select(LedgerPeriod)
            .where(LedgerPeriod.status == PeriodStatus.OPEN)
            .where(LedgerPeriod.end_date <= warning_threshold)
            .order_by(LedgerPeriod.end_date.asc())
        )
        periods = list((await self.db.execute(stmt)).scalars().all())
        return [
            {
                "period_key": p.period_key,
                "end_date": p.end_date.isoformat(),
                "days_until_close": (p.end_date - today).days,
                "fiscal_year": p.fiscal_year,
                "status": p.status,
            }
            for p in periods
        ]

    async def auto_seed_next_fiscal_year_if_needed(self) -> list[LedgerPeriod]:
        """
        LS-BL-07: Automatically seed the next fiscal year's periods when the last open
        period of the current year is within 30 days of its end date.
        Prevents the admin from having to manually create next year's periods.
        """
        today = date.today()
        current_year = today.year
        # Check if all 12 periods for next year exist already
        next_year = current_year + 1
        next_year_key = f"{next_year}-01"
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == next_year_key)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            return []  # Already seeded

        # Check if the last period of this year is near close (within 30 days)
        last_period_key = f"{current_year}-12"
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == last_period_key)
        last_period = (await self.db.execute(stmt)).scalar_one_or_none()
        if last_period and (last_period.end_date - today).days <= 30:
            logger.info(
                "Auto-seeding fiscal year periods",
                extra={"next_year": next_year, "triggered_by": "auto_seed"}
            )
            return await self.seed_fiscal_year(next_year)

        return []
