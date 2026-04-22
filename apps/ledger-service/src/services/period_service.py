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
            period = LedgerPeriod(
                period_key=period_key,
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
        """Close an accounting period."""
        period = await self.get_or_create_period(period_key)
        if period.status == PeriodStatus.CLOSED:
            raise ValueError(f"Period {period_key} is already closed")
            
        period.status = PeriodStatus.CLOSED
        period.closed_at = datetime.now(timezone.utc)
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

    async def list_periods(self, limit: int = 12) -> list[LedgerPeriod]:
        """List periods ordered by date descending."""
        stmt = select(LedgerPeriod).order_by(LedgerPeriod.start_date.desc()).limit(limit)
        return list((await self.db.execute(stmt)).scalars().all())
