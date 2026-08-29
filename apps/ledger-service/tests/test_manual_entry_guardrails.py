from __future__ import annotations

"""
Regression tests for two app-layer guardrails on manual journal postings:

1. Unbalanced entries must be rejected (posting_engine.assert_balanced(), via
   AccountingService._create_balanced_entry()) BEFORE anything is written to
   the database. Nothing in the suite exercised this before -- every existing
   test only posts pre-balanced lines.

2. `AccountingService._reject_manual_credit_to_late_fee_collections` (LS-HIGH-03):
   manual postings (record_manual_entry / record_manual_adjustment) must
   reject any line that CREDITS account 4003 (late_fee_collections), while
   still allowing credits to any other account and allowing DEBITS to 4003
   (the legitimate year-end period-close zeroing entry).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sk_shared.models.ledger import JournalEntry, JournalEntryLine, LedgerAccount, LedgerPeriod
from src.accounting.accounts import ACCOUNT_CODES
from src.services.accounting_service import AccountingService
from src.services.period_service import PeriodService

pytestmark = pytest.mark.asyncio

SUPER_ADMIN = {"X-Actor-Type": "admin", "X-Actor-Roles": "super_admin"}


# ---------------------------------------------------------------------------
# Item: unbalanced entries must be rejected at the app layer, before any
# write to the DB.
# ---------------------------------------------------------------------------


async def test_record_manual_entry_rejects_unbalanced_lines_before_write(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)

    with pytest.raises(ValueError, match="JOURNAL_ENTRY_NOT_BALANCED"):
        await service.record_manual_entry(
            lines=[
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 100.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["owner_equity"], "debit_amount": 0.0, "credit_amount": 40.0},
            ],
            description="Unbalanced manual entry attempt",
            reference="UNBAL-TEST-1",
        )

    # Nothing must have been written -- not the JournalEntry, not any line.
    entries = (
        (await db_session.execute(select(JournalEntry).where(JournalEntry.source_id == "UNBAL-TEST-1")))
        .scalars()
        .all()
    )
    assert entries == []
    lines = (await db_session.execute(select(JournalEntryLine))).scalars().all()
    assert lines == []


async def test_manual_entry_api_rejects_unbalanced_lines_with_400(client, seed_ledger_accounts):
    response = await client.post(
        "/entries/manual",
        json={
            "description": "Unbalanced manual entry via API",
            "lines": [
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 100.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["owner_equity"], "debit_amount": 0.0, "credit_amount": 40.0},
            ],
        },
        headers=SUPER_ADMIN,
    )
    assert response.status_code == 400
    assert "JOURNAL_ENTRY_NOT_BALANCED" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Item: guardrail blocking manual CREDITS to late_fee_collections (4003).
# ---------------------------------------------------------------------------


async def test_manual_entry_credit_to_late_fee_collections_rejected(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)

    with pytest.raises(ValueError, match="MANUAL_CREDIT_TO_LATE_FEE_COLLECTIONS_BLOCKED"):
        await service.record_manual_entry(
            lines=[
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 50.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["late_fee_collections"], "debit_amount": 0.0, "credit_amount": 50.0},
            ],
            description="Attempted manual credit to 4003",
            reference="BLOCKED-CREDIT-4003",
        )

    entries = (
        (
            await db_session.execute(
                select(JournalEntry).where(JournalEntry.source_id == "BLOCKED-CREDIT-4003")
            )
        )
        .scalars()
        .all()
    )
    assert entries == []


async def test_manual_adjustment_credit_to_late_fee_collections_rejected(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)

    with pytest.raises(ValueError, match="MANUAL_CREDIT_TO_LATE_FEE_COLLECTIONS_BLOCKED"):
        await service.record_manual_adjustment(
            adjustment_id="ADJ-BLOCKED-1",
            amount=Decimal("30.00"),
            account_code=ACCOUNT_CODES["late_fee_collections"],
            counter_account_code=ACCOUNT_CODES["cash"],
            debit_to_account=False,  # credits account_code (4003), debits counter (cash)
            description="Attempted manual adjustment crediting 4003",
        )

    entries = (
        (await db_session.execute(select(JournalEntry).where(JournalEntry.source_id == "ADJ-BLOCKED-1")))
        .scalars()
        .all()
    )
    assert entries == []


async def test_manual_entry_credit_to_other_account_still_works(db_session, seed_ledger_accounts):
    """Proves the guardrail isn't overly broad: crediting any account OTHER
    than 4003 (late_fee_collections) via a manual entry must still work."""
    service = AccountingService(db_session)

    result = await service.record_manual_entry(
        lines=[
            {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 75.0, "credit_amount": 0.0},
            {"account_code": ACCOUNT_CODES["affiliate_commission"], "debit_amount": 0.0, "credit_amount": 75.0},
        ],
        description="Legitimate manual entry crediting a different revenue account",
        reference="ALLOWED-CREDIT-4002",
    )
    assert result.created is True

    entry = (
        await db_session.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .where(JournalEntry.source_id == "ALLOWED-CREDIT-4002")
        )
    ).scalar_one()
    assert entry.total_credit == Decimal("75.00")
    credited_codes = {line.account.account_code for line in entry.lines if line.credit_amount > 0}
    assert credited_codes == {ACCOUNT_CODES["affiliate_commission"]}


async def test_manual_entry_api_credit_to_late_fee_collections_rejected_with_400(client, seed_ledger_accounts):
    response = await client.post(
        "/entries/manual",
        json={
            "description": "Attempted manual credit to 4003 via API",
            "lines": [
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 20.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["late_fee_collections"], "debit_amount": 0.0, "credit_amount": 20.0},
            ],
        },
        headers=SUPER_ADMIN,
    )
    assert response.status_code == 400
    assert "MANUAL_CREDIT_TO_LATE_FEE_COLLECTIONS_BLOCKED" in response.json()["detail"]


async def test_period_close_debit_to_late_fee_collections_not_blocked(db_session, seed_ledger_accounts):
    """The guardrail must only block CREDITS to 4003, not the legitimate
    period-close DEBIT that zeroes out any balance in that account
    (PeriodService.close_period, when period_key ends in "-12", routes
    through AccountingService.record_manual_entry -- the same guarded path
    the tests above assert is BLOCKED for credits).

    Since the guardrail blocks all manual credits to 4003 and the automated
    late-fee path never touches 4003 at all, the only way this account could
    ever carry a balance today is pre-existing/legacy data (per its own
    "legacy reporting bucket" documentation) -- so this test seeds that
    balance directly via the ORM (bypassing AccountingService entirely, the
    way a legacy/bulk-load record would have landed) rather than through a
    guarded service method.
    """
    accounts = {row.account_code: row for row in (await db_session.execute(select(LedgerAccount))).scalars().all()}
    cash_account = accounts[ACCOUNT_CODES["cash"]]
    late_fee_account = accounts[ACCOUNT_CODES["late_fee_collections"]]

    legacy_amount = Decimal("40.00")
    legacy_entry = JournalEntry(
        entry_number="JE-LEGACY-4003-0001",
        entry_date=date(2026, 12, 10),
        description="Legacy pre-guardrail credit to late_fee_collections",
        entry_type="legacy",
        source_type="legacy.import",
        source_id=555001,
        is_balanced=True,
        total_debit=legacy_amount,
        total_credit=legacy_amount,
        currency="PKR",
        period_key="2026-12",
    )
    db_session.add(legacy_entry)
    await db_session.flush()
    db_session.add_all(
        [
            JournalEntryLine(
                journal_id=legacy_entry.id,
                account_id=cash_account.id,
                debit_amount=legacy_amount,
                credit_amount=Decimal("0.00"),
                currency="PKR",
            ),
            JournalEntryLine(
                journal_id=legacy_entry.id,
                account_id=late_fee_account.id,
                debit_amount=Decimal("0.00"),
                credit_amount=legacy_amount,
                currency="PKR",
            ),
        ]
    )
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

    accounting = AccountingService(db_session)
    balance_before = await accounting.get_account_balance(ACCOUNT_CODES["late_fee_collections"], as_of="2026-12-31")
    assert Decimal(str(balance_before["balance"])) == legacy_amount

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
    lines_by_account = {line.account.account_code: line for line in closing_entry.lines}

    # The closing entry must DEBIT 4003 to zero it out, and the guardrail
    # must not have blocked this (it only inspects credit_amount).
    assert lines_by_account[ACCOUNT_CODES["late_fee_collections"]].debit_amount == legacy_amount
    assert lines_by_account[ACCOUNT_CODES["late_fee_collections"]].credit_amount == Decimal("0.00")

    balance_after = await accounting.get_account_balance(ACCOUNT_CODES["late_fee_collections"], as_of="2026-12-31")
    assert Decimal(str(balance_after["balance"])) == Decimal("0.00")
