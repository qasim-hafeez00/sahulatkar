from datetime import date
import pytest
from sk_shared.models.ledger import LedgerPeriod
from src.services.period_service import PeriodService


@pytest.mark.asyncio
async def test_close_and_reopen_period(db_session):
    # Supply fiscal_year to satisfy the NOT NULL constraint
    db_session.add(
        LedgerPeriod(
            period_key="2026-04",
            fiscal_year=2026,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            status="open",
        )
    )
    await db_session.commit()

    service = PeriodService(db_session)

    closed = await service.close_period("2026-04", "admin-1")
    assert closed.status == "closed"
    assert closed.closed_by == "admin-1"

    reopened = await service.reopen_period("2026-04")
    assert reopened.status == "open"


@pytest.mark.asyncio
async def test_ensure_period_open_raises_for_closed_period(db_session):
    # Supply fiscal_year to satisfy the NOT NULL constraint
    db_session.add(
        LedgerPeriod(
            period_key="2026-04",
            fiscal_year=2026,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            status="closed",
        )
    )
    await db_session.commit()

    service = PeriodService(db_session)
    with pytest.raises(ValueError, match="PERIOD_CLOSED"):
        await service.ensure_period_open(date(2026, 4, 10))


@pytest.mark.asyncio
async def test_get_period_status_returns_open_if_auto_created(db_session):
    # The new PeriodService auto-creates periods as 'open' if they don't exist
    service = PeriodService(db_session)
    period = await service.get_or_create_period("2026-05")
    assert period.status == "open"
    assert period.period_key == "2026-05"
    assert period.fiscal_year == 2026
