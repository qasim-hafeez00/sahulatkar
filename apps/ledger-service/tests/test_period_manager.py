from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sk_shared.models.ledger import JournalEntry, JournalEntryLine, LedgerPeriod
from src.accounting.accounts import ACCOUNT_CODES
from src.services.accounting_service import AccountingService
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


@pytest.mark.asyncio
async def test_close_year_end_period_posts_balanced_closing_entry(db_session, seed_ledger_accounts):
    """
    P1 regression: closing a fiscal year's final (`-12`) period used to crash
    (wrong PostingLine import, wrong get_account_balance kwarg, and
    record_manual_entry called with kwargs it doesn't accept). This exercises
    the full year-end close with real revenue (murabaha profit) and expense
    (merchant COGS) entries and asserts a balanced closing entry lands.
    """
    accounting = AccountingService(db_session)

    purchase = await accounting.record_purchase(
        order_id=9001, cost_amount=Decimal("100.00"), total_amount=Decimal("140.00"), vcn_id=9001
    )
    merchant_payment = await accounting.record_merchant_payment(order_id=9001, amount=Decimal("15.00"))

    # Pin both entries into the fiscal year's final period.
    purchase.journal_entry.entry_date = date(2026, 12, 15)
    purchase.journal_entry.period_key = "2026-12"
    merchant_payment.journal_entry.entry_date = date(2026, 12, 20)
    merchant_payment.journal_entry.period_key = "2026-12"
    await db_session.commit()

    db_session.add(
        LedgerPeriod(
            period_key="2026-12",
            fiscal_year=2026,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 31),
            status="open",
        )
    )
    await db_session.commit()

    period_service = PeriodService(db_session)
    closed = await period_service.close_period("2026-12", "admin-1")
    assert closed.status == "closed"

    closing_entry = (
        await db_session.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .where(JournalEntry.description == "Annual closing entry for fiscal year 2026")
        )
    ).scalar_one()
    assert closing_entry.is_balanced is True
    assert closing_entry.total_debit == closing_entry.total_credit
    # Revenue (40 profit) exceeds expense (15 COGS): net income of 25 should
    # land as a credit to retained earnings.
    assert Decimal(str(closing_entry.total_debit)) == Decimal("40.00")

    lines_by_account = {
        line.account.account_code: line
        for line in closing_entry.lines
    }
    assert lines_by_account[ACCOUNT_CODES["murabaha_profit"]].debit_amount == Decimal("40.00")
    assert lines_by_account[ACCOUNT_CODES["cogs_merchant_payment"]].credit_amount == Decimal("15.00")
    assert lines_by_account[ACCOUNT_CODES["retained_earnings"]].credit_amount == Decimal("25.00")
