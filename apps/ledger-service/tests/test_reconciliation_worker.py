from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.payment import PaymentTransaction, Reconciliation, ReconciliationItem
from src.workers import reconciliation_worker


class _SessionContextManager:
    """Wraps an already-open AsyncSession so `async with SessionLocal() as
    session:` (as used by every worker's main()) yields the test's real
    db_session instead of opening a connection to the production database
    configured in src.core.database.SessionLocal."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _patch_session(monkeypatch, module, session) -> None:
    monkeypatch.setattr(module, "SessionLocal", lambda: _SessionContextManager(session))


def test_build_parser_parses_all_fields():
    parser = reconciliation_worker._build_parser()
    args = parser.parse_args(
        [
            "--gateway", "safepay",
            "--settlement-date", "2026-04-10",
            "--expected-amount", "100.00",
            "--actual-amount", "120.00",
            "--reference", "ref-1",
            "--notes", "note",
        ]
    )
    assert args.gateway == "safepay"
    assert args.settlement_date == "2026-04-10"
    assert args.expected_amount == Decimal("100.00")
    assert args.actual_amount == Decimal("120.00")
    assert args.reference == "ref-1"
    assert args.notes == "note"


def test_load_payload_from_file_rejects_non_object_json(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        reconciliation_worker._load_payload_from_file(path)


def test_load_payload_from_file_propagates_invalid_json_syntax(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        reconciliation_worker._load_payload_from_file(path)


@pytest.mark.asyncio
async def test_main_raises_when_required_cli_field_missing(db_session, monkeypatch):
    _patch_session(monkeypatch, reconciliation_worker, db_session)

    with pytest.raises(ValueError, match="actual_amount"):
        await reconciliation_worker.main(
            [
                "--gateway", "safepay",
                "--settlement-date", "2026-04-10",
                "--expected-amount", "100.00",
            ]
        )


@pytest.mark.asyncio
async def test_main_imports_snapshot_from_cli_args(db_session, monkeypatch):
    """A real matching PaymentTransaction must exist for the gateway/date for
    the snapshot to come back "matched" -- expected == actual alone is not
    enough (see LS-BL-06: the matched-transaction sum is also compared
    against both amounts, so a phantom settlement with no real transactions
    is correctly flagged "discrepant" instead of trusted at face value)."""
    _patch_session(monkeypatch, reconciliation_worker, db_session)

    txn = PaymentTransaction(
        user_id=301,
        gateway="safepay",
        amount=Decimal("100.00"),
        currency="PKR",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()
    settlement_date = (txn.created_at.date() if txn.created_at else date.today()).isoformat()

    await reconciliation_worker.main(
        [
            "--gateway", "safepay",
            "--settlement-date", settlement_date,
            "--expected-amount", "100.00",
            "--actual-amount", "100.00",
        ]
    )

    reconciliation = (
        await db_session.execute(select(Reconciliation).where(Reconciliation.gateway == "safepay"))
    ).scalar_one()
    assert reconciliation.status == "matched"


@pytest.mark.asyncio
async def test_main_persists_reference_and_notes_from_cli_args(db_session, monkeypatch):
    """--reference/--notes must reach ReconciliationService.import_snapshot and
    be persisted (gateway_ref on the created ReconciliationItem, notes on the
    Reconciliation row) -- not silently dropped or replaced with None."""
    _patch_session(monkeypatch, reconciliation_worker, db_session)

    txn = PaymentTransaction(
        user_id=302,
        gateway="safepay",
        amount=Decimal("100.00"),
        currency="PKR",
        status="success",
    )
    db_session.add(txn)
    await db_session.commit()
    settlement_date = (txn.created_at.date() if txn.created_at else date.today()).isoformat()

    await reconciliation_worker.main(
        [
            "--gateway", "safepay",
            "--settlement-date", settlement_date,
            "--expected-amount", "100.00",
            "--actual-amount", "100.00",
            "--reference", "gw-ref-123",
            "--notes", "manual note",
        ]
    )

    reconciliation = (
        await db_session.execute(select(Reconciliation).where(Reconciliation.gateway == "safepay"))
    ).scalar_one()
    assert reconciliation.notes == "manual note"

    item = (
        await db_session.execute(
            select(ReconciliationItem).where(ReconciliationItem.reconciliation_id == reconciliation.id)
        )
    ).scalar_one()
    assert item.gateway_ref == "gw-ref-123"


@pytest.mark.asyncio
async def test_main_treats_empty_string_field_as_missing(db_session, monkeypatch):
    """An empty-string CLI value (e.g. --gateway "") must be treated the same
    as an omitted field, not accepted as a valid blank gateway name."""
    _patch_session(monkeypatch, reconciliation_worker, db_session)

    with pytest.raises(ValueError, match="gateway"):
        await reconciliation_worker.main(
            [
                "--gateway", "",
                "--settlement-date", "2026-04-10",
                "--expected-amount", "100.00",
                "--actual-amount", "100.00",
            ]
        )


@pytest.mark.asyncio
async def test_main_file_payload_takes_precedence_over_cli_flags(db_session, monkeypatch, tmp_path):
    """main() branches entirely on `if args.file is not None`; any other CLI
    flags passed alongside --file are silently ignored in favor of the file's
    contents. Document/verify that actual (slightly surprising) behavior."""
    _patch_session(monkeypatch, reconciliation_worker, db_session)

    payload = {
        "gateway": "jazzcash",
        "settlement_date": "2026-04-11",
        "expected_amount": "200.00",
        "actual_amount": "190.00",
        "reference": "file-ref",
    }
    file_path = tmp_path / "settlement.json"
    file_path.write_text(json.dumps(payload), encoding="utf-8")

    await reconciliation_worker.main(["--file", str(file_path), "--gateway", "should-be-ignored"])

    reconciliation = (
        await db_session.execute(select(Reconciliation).where(Reconciliation.gateway == "jazzcash"))
    ).scalar_one()
    assert reconciliation.status == "discrepant"
    assert reconciliation.expected_amount == Decimal("200.00")
    assert reconciliation.actual_amount == Decimal("190.00")


@pytest.mark.asyncio
async def test_main_raises_when_file_payload_missing_required_field(db_session, monkeypatch, tmp_path):
    _patch_session(monkeypatch, reconciliation_worker, db_session)

    file_path = tmp_path / "bad.json"
    file_path.write_text(
        json.dumps({"gateway": "safepay", "settlement_date": "2026-04-10", "expected_amount": "100.00"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="actual_amount"):
        await reconciliation_worker.main(["--file", str(file_path)])
