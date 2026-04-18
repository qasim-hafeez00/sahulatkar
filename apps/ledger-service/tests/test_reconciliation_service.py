from __future__ import annotations

from datetime import date
from decimal import Decimal
import json

import pytest

from sk_shared.models.payment import PaymentTransaction
from src.config import settings
from src.services.reconciliation_service import ReconciliationService


@pytest.mark.asyncio
async def test_reconciliation_import_persists_snapshot_and_items(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))

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

    assert result["status"] == "variance"
    assert result["matched_transaction_count"] == 1
    assert result["discrepancy"] == pytest.approx(20.0)

    snapshots_path = tmp_path / "reconciliation_snapshots.jsonl"
    items_path = tmp_path / "reconciliation_items.jsonl"
    assert snapshots_path.exists()
    assert items_path.exists()

    snapshot_payload = json.loads(snapshots_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert snapshot_payload["gateway"] == "safepay"
    assert snapshot_payload["status"] == "variance"

    item_lines = [json.loads(line) for line in items_path.read_text(encoding="utf-8").strip().splitlines() if line.strip()]
    statuses = {item["item_status"] for item in item_lines}
    assert "matched" in statuses
    assert "discrepancy" in statuses


@pytest.mark.asyncio
async def test_reconciliation_query_reads_persisted_snapshots(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
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
