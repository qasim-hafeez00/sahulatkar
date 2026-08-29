from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.payment import PaymentTransaction, Reconciliation, ReconciliationItem
from src.services.reconciliation_service import ReconciliationService


@pytest.mark.asyncio
async def test_reconciliation_import_persists_snapshot_and_items(db_session):
    txn = PaymentTransaction(
        user_id=101,
        gateway="safepay",
        amount=Decimal("120.00"),
        currency="PKR",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()

    service = ReconciliationService(db_session)
    settlement_date = (txn.created_at.date() if txn.created_at else date.today()).isoformat()

    result = await service.import_snapshot(
        gateway="safepay",
        settlement_date=settlement_date,
        expected_amount=Decimal("100.00"),
        actual_amount=Decimal("120.00"),
        reference="ref-101",
        notes="variance expected",
    )

    assert result["status"] == "discrepant"
    assert result["matched_transaction_count"] == 1
    assert result["discrepancy"] == pytest.approx(20.0)

    reconciliation = (
        await db_session.execute(
            select(Reconciliation).where(
                Reconciliation.gateway == "safepay",
                Reconciliation.settlement_date == date.fromisoformat(settlement_date),
            )
        )
    ).scalar_one()
    assert reconciliation.status == "discrepant"

    rows = (
        await db_session.execute(
            select(ReconciliationItem).where(ReconciliationItem.reconciliation_id == reconciliation.id)
        )
    ).scalars().all()
    statuses = {row.status for row in rows}
    assert "matched" in statuses
    assert "discrepant" in statuses


@pytest.mark.asyncio
async def test_reconciliation_query_reads_persisted_snapshots(db_session):
    service = ReconciliationService(db_session)

    await service.import_snapshot(
        gateway="safepay",
        settlement_date="2026-04-10",
        expected_amount=Decimal("100.00"),
        actual_amount=Decimal("100.00"),
        reference="s1",
        notes=None,
    )
    await service.import_snapshot(
        gateway="jazzcash",
        settlement_date="2026-04-11",
        expected_amount=Decimal("200.00"),
        actual_amount=Decimal("190.00"),
        reference="j1",
        notes=None,
    )

    filtered = await service.query_snapshots(gateway="safepay", settlement_date="2026-04-10", page=1, limit=10)
    assert filtered["pagination"]["total"] == 1
    assert filtered["items"][0]["gateway"] == "safepay"

    all_rows = await service.query_snapshots(page=1, limit=10)
    assert all_rows["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_line_items_catches_offsetting_errors_aggregate_check_misses(db_session):
    """LS-MED-04 regression: two local transactions are each mis-reported by
    the gateway in opposite directions (+10 on one, -10 on the other), so
    they net to zero in the aggregate expected/actual comparison -- the
    aggregate check alone would call this reconciliation "matched". Passing
    per-transaction `line_items` must catch both individual mismatches and
    force the overall status to "discrepant"."""
    settlement_date = date(2026, 5, 1)
    txn_a = PaymentTransaction(
        user_id=201,
        gateway="safepay",
        gateway_txn_id="safepay_txn_a",
        amount=Decimal("100.00"),
        currency="PKR",
        status="success",
    )
    txn_b = PaymentTransaction(
        user_id=202,
        gateway="safepay",
        gateway_txn_id="safepay_txn_b",
        amount=Decimal("50.00"),
        currency="PKR",
        status="success",
    )
    db_session.add_all([txn_a, txn_b])
    await db_session.commit()
    await db_session.refresh(txn_a)
    await db_session.refresh(txn_b)
    settlement_date_str = txn_a.created_at.date().isoformat() if txn_a.created_at else settlement_date.isoformat()

    service = ReconciliationService(db_session)

    # Aggregate totals: local sum = 100 + 50 = 150. Gateway's line items also
    # sum to 150 (110 + 40) -- offsetting errors that net to zero overall.
    result = await service.import_snapshot(
        gateway="safepay",
        settlement_date=settlement_date_str,
        expected_amount=Decimal("150.00"),
        actual_amount=Decimal("150.00"),
        reference="ref-offsetting",
        notes=None,
        line_items=[
            {"gateway_txn_id": "safepay_txn_a", "amount": Decimal("110.00")},  # over-reported by 10
            {"gateway_txn_id": "safepay_txn_b", "amount": Decimal("40.00")},  # under-reported by 10
        ],
    )

    assert result["status"] == "discrepant"
    assert result["discrepancy"] == pytest.approx(0.0)
    assert "LINE_LEVEL_MISMATCH" in (result["notes"] or "")
    assert "safepay_txn_a" in result["notes"]
    assert "safepay_txn_b" in result["notes"]

    reconciliation = (
        await db_session.execute(
            select(Reconciliation).where(
                Reconciliation.gateway == "safepay",
                Reconciliation.settlement_date == date.fromisoformat(settlement_date_str),
            )
        )
    ).scalar_one()
    assert reconciliation.status == "discrepant"

    items = (
        (
            await db_session.execute(
                select(ReconciliationItem).where(ReconciliationItem.reconciliation_id == reconciliation.id)
            )
        )
        .scalars()
        .all()
    )
    items_by_ref = {item.gateway_ref: item for item in items}
    assert items_by_ref["safepay_txn_a"].status == "discrepant"
    assert items_by_ref["safepay_txn_a"].expected_amount == Decimal("110.00")
    assert items_by_ref["safepay_txn_a"].actual_amount == Decimal("100.00")
    assert items_by_ref["safepay_txn_b"].status == "discrepant"
    assert items_by_ref["safepay_txn_b"].expected_amount == Decimal("40.00")
    assert items_by_ref["safepay_txn_b"].actual_amount == Decimal("50.00")


@pytest.mark.asyncio
async def test_line_items_all_match_stays_matched(db_session):
    """Sanity counterpart: when every line_item genuinely matches its local
    PaymentTransaction, the line-level check must NOT force a discrepant
    status."""
    settlement_date = date(2026, 5, 2)
    txn = PaymentTransaction(
        user_id=203,
        gateway="jazzcash",
        gateway_txn_id="jazzcash_txn_ok",
        amount=Decimal("75.00"),
        currency="PKR",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()
    await db_session.refresh(txn)
    settlement_date_str = txn.created_at.date().isoformat() if txn.created_at else settlement_date.isoformat()

    service = ReconciliationService(db_session)
    result = await service.import_snapshot(
        gateway="jazzcash",
        settlement_date=settlement_date_str,
        expected_amount=Decimal("75.00"),
        actual_amount=Decimal("75.00"),
        reference="ref-clean",
        notes=None,
        line_items=[{"gateway_txn_id": "jazzcash_txn_ok", "amount": Decimal("75.00")}],
    )

    assert result["status"] == "matched"


@pytest.mark.asyncio
async def test_line_items_omitted_behavior_is_unchanged(db_session):
    """Backward compatibility: when `line_items` is omitted entirely (the
    only mode the CLI worker/admin API currently exercise), behavior must be
    identical to before the line-level feature existed -- every local
    transaction for the gateway/date gets a "matched" ReconciliationItem
    mirroring itself, keyed by the top-level `reference`, and the overall
    status is driven purely by the pre-existing aggregate check."""
    settlement_date = date(2026, 5, 3)
    txn_a = PaymentTransaction(
        user_id=204,
        gateway="safepay",
        gateway_txn_id="safepay_txn_nolines_a",
        amount=Decimal("30.00"),
        currency="PKR",
        status="success",
    )
    txn_b = PaymentTransaction(
        user_id=205,
        gateway="safepay",
        gateway_txn_id="safepay_txn_nolines_b",
        amount=Decimal("20.00"),
        currency="PKR",
        status="success",
    )
    db_session.add_all([txn_a, txn_b])
    await db_session.commit()
    await db_session.refresh(txn_a)
    settlement_date_str = txn_a.created_at.date().isoformat() if txn_a.created_at else settlement_date.isoformat()

    service = ReconciliationService(db_session)
    result = await service.import_snapshot(
        gateway="safepay",
        settlement_date=settlement_date_str,
        expected_amount=Decimal("50.00"),
        actual_amount=Decimal("50.00"),
        reference="ref-no-line-items",
        notes=None,
        # line_items intentionally omitted
    )

    assert result["status"] == "matched"
    assert result["notes"] is None

    reconciliation = (
        await db_session.execute(
            select(Reconciliation).where(
                Reconciliation.gateway == "safepay",
                Reconciliation.settlement_date == date.fromisoformat(settlement_date_str),
            )
        )
    ).scalar_one()
    assert reconciliation.status == "matched"

    items = (
        (
            await db_session.execute(
                select(ReconciliationItem).where(ReconciliationItem.reconciliation_id == reconciliation.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(items) == 2
    assert all(item.status == "matched" for item in items)
    # Pre-existing behavior: gateway_ref mirrors the top-level `reference`,
    # not the individual transaction's gateway_txn_id.
    assert all(item.gateway_ref == "ref-no-line-items" for item in items)
