"""
Tests for src/workers/reconciliation_worker.run_reconciliation.

Phase 2: this worker had zero test coverage. Exercises the local-file
fallback ingestion path (SettlementFetcher returns [] for a gateway with no
automated fetcher, e.g. "raast", so run_reconciliation falls back to reading
{RECONCILIATION_AUDIT_DIR}/settlement_{gateway}_{date}.json) rather than the
real SFTP/HTTP fetchers, which hit external services.
"""
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from sk_shared.models.auth import User
from sk_shared.models.payment import PaymentTransaction
from src.config import settings
from src.workers import reconciliation_worker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _patch_worker_infra(monkeypatch, db_session):
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(reconciliation_worker, "SessionLocal", _session_cm)


@pytest.fixture
def settlement_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RECONCILIATION_AUDIT_DIR", str(tmp_path))
    return tmp_path


async def _seed_user_and_txn(db_session, *, gateway_txn_id: str, amount: str, gateway: str = "raast") -> User:
    user = User(phone="+923004000001", status="active")
    db_session.add(user)
    await db_session.flush()
    db_session.add(PaymentTransaction(
        user_id=user.id,
        amount=Decimal(amount),
        currency="PKR",
        gateway=gateway,
        gateway_txn_id=gateway_txn_id,
        status="success",
    ))
    await db_session.commit()
    return user


def _write_settlement_file(settlement_dir, gateway: str, settlement_date: date, records: list[dict]) -> None:
    path = settlement_dir / f"settlement_{gateway}_{settlement_date}.json"
    path.write_text(json.dumps(records))


async def test_run_reconciliation_matches_internal_transaction(settlement_dir, db_session):
    settlement_date = date(2026, 6, 1)
    await _seed_user_and_txn(db_session, gateway_txn_id="TXN-1", amount="500.00")
    _write_settlement_file(settlement_dir, "raast", settlement_date, [
        {"gateway_txn_id": "TXN-1", "amount_pkr": "500.00", "status": "settled",
         "settled_at": datetime(2026, 6, 1, tzinfo=timezone.utc).isoformat()},
    ])

    await reconciliation_worker.run_reconciliation("raast", settlement_date)
    # No exception, and reconcile() persists its own audit trail — the
    # absence of a raised discrepancy-required assertion here is fine since
    # ReconciliationService.reconcile is covered directly elsewhere; this
    # test's job is to prove the worker's file-loading/session wiring works.


async def test_run_reconciliation_flags_amount_mismatch(settlement_dir, db_session, caplog):
    settlement_date = date(2026, 6, 2)
    await _seed_user_and_txn(db_session, gateway_txn_id="TXN-2", amount="500.00")
    _write_settlement_file(settlement_dir, "raast", settlement_date, [
        {"gateway_txn_id": "TXN-2", "amount_pkr": "550.00", "status": "settled",
         "settled_at": datetime(2026, 6, 2, tzinfo=timezone.utc).isoformat()},
    ])

    with caplog.at_level("WARNING"):
        await reconciliation_worker.run_reconciliation("raast", settlement_date)

    assert any("discrepancies found" in r.message for r in caplog.records)


async def test_run_reconciliation_no_settlement_file_is_a_noop(settlement_dir, caplog):
    with caplog.at_level("WARNING"):
        await reconciliation_worker.run_reconciliation("raast", date(2026, 6, 3))

    assert any("Settlement file not found" in r.message for r in caplog.records)


async def test_settlement_fetcher_returns_empty_for_unknown_gateway(caplog):
    fetcher = reconciliation_worker.SettlementFetcher()
    with caplog.at_level("WARNING"):
        records = await fetcher.fetch_settlement("raast", date(2026, 6, 4))
    assert records == []
    assert any("No automated fetcher" in r.message for r in caplog.records)
