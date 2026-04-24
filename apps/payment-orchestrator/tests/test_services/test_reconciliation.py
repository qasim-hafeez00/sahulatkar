"""
Tests for ReconciliationService.
Target: 12 test cases
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.schemas.reconciliation import ReconciliationImportRequest, ReconciliationRecord
from src.services.reconciliation import ReconciliationService

pytestmark = pytest.mark.asyncio


def _make_request(gateway: str, records: list) -> ReconciliationImportRequest:
    return ReconciliationImportRequest(
        gateway=gateway,
        settlement_date=date.today(),
        records=records,
    )


async def test_reconciliation_all_matched(db_session, test_user, seed_order_with_loan):
    """All gateway records match internal transactions."""
    from sk_shared.models.payment import PaymentTransaction
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)

    # Seed a matching transaction
    txn = PaymentTransaction(
        loan_id=loan.id,
        user_id=user.id,
        amount=Decimal("975"),
        currency="PKR",
        gateway="jazzcash",
        gateway_txn_id="jc_match_001",
        status="success",
        reconciled_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.commit()

    service = ReconciliationService(db_session)
    report = await service.reconcile(_make_request("jazzcash", [
        ReconciliationRecord(
            gateway_txn_id="jc_match_001",
            amount_pkr=Decimal("975"),
            status="success",
            settled_at=datetime.now(timezone.utc),
        )
    ]))

    assert report.matched == 1
    assert report.discrepancies == 0
    assert report.net_discrepancy == Decimal("0.00")


async def test_reconciliation_detects_missing_internally(db_session):
    """Gateway record has no matching internal transaction."""
    service = ReconciliationService(db_session)
    report = await service.reconcile(_make_request("safepay", [
        ReconciliationRecord(
            gateway_txn_id="sp_ghost_001",
            amount_pkr=Decimal("1300"),
            status="success",
            settled_at=datetime.now(timezone.utc),
        )
    ]))

    assert report.discrepancies == 1
    assert report.items[0].match_status == "missing_internally"


async def test_reconciliation_detects_amount_mismatch(db_session, test_user, seed_order_with_loan):
    """Gateway amount differs from internal amount."""
    from sk_shared.models.payment import PaymentTransaction
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)

    txn = PaymentTransaction(
        loan_id=loan.id,
        user_id=user.id,
        amount=Decimal("975"),
        currency="PKR",
        gateway="safepay",
        gateway_txn_id="sp_mismatch_001",
        status="success",
        reconciled_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.commit()

    service = ReconciliationService(db_session)
    report = await service.reconcile(_make_request("safepay", [
        ReconciliationRecord(
            gateway_txn_id="sp_mismatch_001",
            amount_pkr=Decimal("970"),   # Different from 975
            status="success",
            settled_at=datetime.now(timezone.utc),
        )
    ]))

    assert report.discrepancies == 1
    assert report.items[0].match_status == "amount_mismatch"
    assert report.items[0].discrepancy_amount == Decimal("5")


async def test_reconciliation_detects_missing_in_gateway(db_session, test_user, seed_order_with_loan):
    """Internal transaction not present in gateway settlement file."""
    from sk_shared.models.payment import PaymentTransaction
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)

    # Internal transaction that wasn't in the settlement file
    txn = PaymentTransaction(
        loan_id=loan.id,
        user_id=user.id,
        amount=Decimal("975"),
        currency="PKR",
        gateway="raast",
        gateway_txn_id="raast_ghost_internal",
        status="success",
        reconciled_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.commit()

    service = ReconciliationService(db_session)
    # Empty gateway settlement file
    report = await service.reconcile(_make_request("raast", []))

    assert report.discrepancies == 1
    assert report.items[0].match_status == "missing_in_gateway"


async def test_reconciliation_empty_both_sides(db_session):
    service = ReconciliationService(db_session)
    report = await service.reconcile(_make_request("jazzcash", []))
    assert report.matched == 0
    assert report.discrepancies == 0
    assert report.net_discrepancy == Decimal("0.00")


async def test_reconciliation_report_contains_all_items(db_session, test_user, seed_order_with_loan):
    """Report should include items for all records checked."""
    from sk_shared.models.payment import PaymentTransaction
    user, _ = test_user
    order, loan = await seed_order_with_loan(user.id)

    txn = PaymentTransaction(
        loan_id=loan.id, user_id=user.id, amount=Decimal("500"),
        currency="PKR", gateway="jazzcash", gateway_txn_id="jc_bulk_1",
        status="success", reconciled_at=datetime.now(timezone.utc),
    )
    db_session.add(txn)
    await db_session.commit()

    service = ReconciliationService(db_session)
    report = await service.reconcile(_make_request("jazzcash", [
        ReconciliationRecord(gateway_txn_id="jc_bulk_1", amount_pkr=Decimal("500"), status="success", settled_at=datetime.now(timezone.utc)),
        ReconciliationRecord(gateway_txn_id="jc_bulk_2", amount_pkr=Decimal("500"), status="success", settled_at=datetime.now(timezone.utc)),
    ]))

    assert report.total_records == 2
    assert len(report.items) == 2   # jc_bulk_1 (match) + jc_bulk_2 (missing internally)


async def test_reconciliation_net_discrepancy_calculation(db_session):
    """Net discrepancy = total_gateway_amount - total_internal_amount."""
    service = ReconciliationService(db_session)
    report = await service.reconcile(_make_request("safepay", [
        ReconciliationRecord(gateway_txn_id="sp_extra", amount_pkr=Decimal("1000"), status="success", settled_at=datetime.now(timezone.utc)),
    ]))
    # 1000 from gateway, 0 internally
    assert report.net_discrepancy == Decimal("1000")
