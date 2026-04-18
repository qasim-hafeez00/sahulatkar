from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sk_shared.models.ledger import JournalEntry, JournalEntryLine
from src.services.accounting_service import AccountingService


@pytest.mark.asyncio
async def test_accounting_additional_journal_workflows(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)

    await service.record_vcn_load(vcn_id=1001, amount=Decimal("500.00"))
    await service.record_merchant_payment(order_id=2001, amount=Decimal("500.00"))
    await service.record_gateway_fee(transaction_id=3001, amount=Decimal("25.00"))
    await service.record_refund(transaction_id=4001, amount=Decimal("100.00"))
    await service.record_chargeback(transaction_id=5001, amount=Decimal("60.00"))
    await service.record_provision(provision_id=6001, amount=Decimal("150.00"))
    await service.record_write_off(write_off_id=7001, amount=Decimal("100.00"))
    await service.record_manual_adjustment(
        adjustment_id=8001,
        amount=Decimal("10.00"),
        account_code="1001",
        counter_account_code="3001",
        debit_to_account=True,
        description="Ops correction",
    )

    count_stmt = select(JournalEntry).where(
        JournalEntry.source_type.in_(
            [
                "vcn.load",
                "merchant.payment",
                "payment.gateway_fee",
                "payment.refund",
                "payment.chargeback",
                "loan.provision",
                "loan.write_off",
                "ledger.manual_adjustment",
            ]
        )
    )
    rows = (await db_session.execute(count_stmt)).scalars().all()
    assert len(rows) == 8
    assert all(row.total_debit == row.total_credit for row in rows)


@pytest.mark.asyncio
async def test_reversal_creates_inverse_lines(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    await service.record_gateway_fee(transaction_id=9101, amount=Decimal("22.00"))

    original = (
        await db_session.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .where(JournalEntry.source_type == "payment.gateway_fee", JournalEntry.source_id == 9101)
        )
    ).scalar_one()

    reversal = await service.record_reversal(
        reversal_id=9201,
        original_source_type="payment.gateway_fee",
        original_source_id=9101,
        reason="fee waived",
    )

    reversed_entry = (
        await db_session.execute(
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .where(JournalEntry.id == reversal.journal_entry.id)
        )
    ).scalar_one()

    assert original.total_debit == reversed_entry.total_credit
    assert original.total_credit == reversed_entry.total_debit
    assert reversed_entry.entry_type == "reversal"
    assert reversed_entry.source_type == "ledger.reversal"


@pytest.mark.asyncio
async def test_reversal_raises_when_original_missing(db_session, seed_ledger_accounts):
    service = AccountingService(db_session)
    with pytest.raises(LookupError, match="ORIGINAL_ENTRY_NOT_FOUND"):
        await service.record_reversal(
            reversal_id=9999,
            original_source_type="payment.gateway_fee",
            original_source_id=9999,
        )
