"""
Accounting Period Management

Manages accounting period lifecycle (open, close, reopen) to prevent posting
to closed periods and maintain period integrity for financial reporting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import LedgerPeriod


@dataclass(slots=True)
class AccountingPeriod:
    """Represents a single accounting period (month or quarter)."""
    period_key: str  # Format: YYYY-MM or YYYY-QN
    start_date: date
    end_date: date
    status: Literal["open", "closed"]
    closed_at: datetime | None = None
    closed_by: str | None = None  # Admin user ID
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "period_key": self.period_key,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "status": self.status,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "closed_by": self.closed_by,
        }


class PeriodClosingError(Exception):
    """Raised when attempting invalid period operations."""
    pass


class PeriodManager:
    """
    Manages accounting period lifecycle.
    
    Supports:
    - Marking periods as closed (prevents posting)
    - Reopening periods (allows corrections)
    - Querying period status
    """
    
    @staticmethod
    def parse_period_key(period_key: str) -> tuple[int, int | str]:
        """
        Parse period key to extract year and month/quarter.
        
        Args:
            period_key: Format YYYY-MM or YYYY-QN (e.g., 2024-01 or 2024-Q1)
            
        Returns:
            Tuple of (year, month_or_quarter)
            
        Raises:
            ValueError: If format is invalid
        """
        # Match YYYY-MM (monthly) or YYYY-QN (quarterly)
        month_match = re.match(r"^(\d{4})-(\d{2})$", period_key)
        quarter_match = re.match(r"^(\d{4})-(Q[1-4])$", period_key)
        
        if month_match:
            year = int(month_match.group(1))
            month = int(month_match.group(2))
            if not 1 <= month <= 12:
                raise ValueError(f"Invalid month in period_key: {period_key}")
            return year, month
        elif quarter_match:
            year = int(quarter_match.group(1))
            quarter = quarter_match.group(2)
            return year, quarter
        else:
            raise ValueError(f"Invalid period_key format: {period_key}. Expected YYYY-MM or YYYY-QN.")

    @staticmethod
    def get_period_bounds(period_key: str) -> tuple[date, date]:
        """
        Get start and end dates for a period.
        
        Args:
            period_key: Format YYYY-MM or YYYY-QN
            
        Returns:
            Tuple of (start_date, end_date)
        """
        year, month_or_quarter = PeriodManager.parse_period_key(period_key)
        
        if isinstance(month_or_quarter, int):  # Monthly period
            month = month_or_quarter
            start = date(year, month, 1)
            # End date is last day of month
            if month == 12:
                end = date(year + 1, 1, 1)
            else:
                end = date(year, month + 1, 1)
            end = date(end.year, end.month, end.day - 1) if end.day > 1 else date(end.year, end.month - 1, 1)
        else:  # Quarterly period (Q1-Q4)
            quarter = int(month_or_quarter[1])
            start_month = (quarter - 1) * 3 + 1
            start = date(year, start_month, 1)
            end_month = start_month + 2
            end_year = year
            if end_month > 12:
                end_month -= 12
                end_year += 1
            # End date is last day of quarter
            if end_month == 12:
                end = date(end_year + 1, 1, 1)
            else:
                end = date(end_year, end_month + 1, 1)
            end = date(end.year, end.month, end.day - 1) if end.day > 1 else date(end.year, end.month - 1, 1)
        
        return start, end

    async def close_period(
        self,
        db_session: AsyncSession,
        period_key: str,
        closed_by: str | None = None,
    ) -> AccountingPeriod:
        """
        Close an accounting period.
        
        Once closed, no journal entries can be posted to this period.
        
        Args:
            db_session: Database session
            period_key: Period to close (YYYY-MM or YYYY-QN)
            closed_by: Admin ID performing the close (for audit)
            
        Returns:
            Updated AccountingPeriod
            
        Raises:
            PeriodClosingError: If period already closed or doesn't exist
        """
        # Check if period exists and is open
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == period_key)
        result = await db_session.execute(stmt)
        period_record = result.scalars().first()
        
        if period_record is None:
            raise PeriodClosingError(f"Period {period_key} not found.")
        
        if period_record.status == "closed":
            raise PeriodClosingError(f"Period {period_key} is already closed.")
        
        # Mark period as closed
        period_record.status = "closed"
        period_record.closed_at = datetime.now(timezone.utc)
        period_record.closed_by = closed_by
        
        await db_session.flush()
        
        start, end = self.get_period_bounds(period_key)
        return AccountingPeriod(
            period_key=period_key,
            start_date=start,
            end_date=end,
            status="closed",
            closed_at=period_record.closed_at,
            closed_by=closed_by,
        )

    async def reopen_period(
        self,
        db_session: AsyncSession,
        period_key: str,
    ) -> AccountingPeriod:
        """
        Reopen a closed period.
        
        Allows corrections to be posted (use with caution).
        
        Args:
            db_session: Database session
            period_key: Period to reopen
            
        Returns:
            Updated AccountingPeriod
            
        Raises:
            PeriodClosingError: If period not closed or doesn't exist
        """
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == period_key)
        result = await db_session.execute(stmt)
        period_record = result.scalars().first()
        
        if period_record is None:
            raise PeriodClosingError(f"Period {period_key} not found.")
        
        if period_record.status != "closed":
            raise PeriodClosingError(f"Period {period_key} is not closed.")
        
        period_record.status = "open"
        period_record.closed_at = None
        period_record.closed_by = None
        
        await db_session.flush()
        
        start, end = self.get_period_bounds(period_key)
        return AccountingPeriod(
            period_key=period_key,
            start_date=start,
            end_date=end,
            status="open",
        )

    async def get_period_status(
        self,
        db_session: AsyncSession,
        period_key: str,
    ) -> AccountingPeriod | None:
        """
        Get the status of a period.
        
        Args:
            db_session: Database session
            period_key: Period to check
            
        Returns:
            AccountingPeriod or None if not found
        """
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == period_key)
        result = await db_session.execute(stmt)
        period_record = result.scalars().first()
        
        if period_record is None:
            return None
        
        start, end = self.get_period_bounds(period_key)
        return AccountingPeriod(
            period_key=period_key,
            start_date=start,
            end_date=end,
            status=period_record.status,
            closed_at=period_record.closed_at,
            closed_by=period_record.closed_by,
        )

    async def check_period_closed(
        self,
        db_session: AsyncSession,
        target_date: date,
    ) -> bool:
        """
        Check if the period containing target_date is closed.
        
        Args:
            db_session: Database session
            target_date: Date to check
            
        Returns:
            True if period is closed, False if open or not found
        """
        # Determine period key for target_date (use monthly by default)
        period_key = target_date.strftime("%Y-%m")
        
        stmt = select(LedgerPeriod).where(LedgerPeriod.period_key == period_key)
        result = await db_session.execute(stmt)
        period_record = result.scalars().first()
        
        if period_record is None:
            # Period doesn't exist yet, so it's "open"
            return False
        
        return period_record.status == "closed"

    async def ensure_period_open(
        self,
        db_session: AsyncSession,
        target_date: date,
    ) -> None:
        """
        Ensure period is open, raising if closed.
        
        Useful as a guard in record_* methods.
        
        Args:
            db_session: Database session
            target_date: Date being posted to
            
        Raises:
            PeriodClosingError: If period is closed
        """
        is_closed = await self.check_period_closed(db_session, target_date)
        if is_closed:
            period_key = target_date.strftime("%Y-%m")
            raise PeriodClosingError(
                f"Cannot post to closed period {period_key}. Period must be reopened first."
            )
