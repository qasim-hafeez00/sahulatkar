from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.ledger import LedgerAccountBalance
from src.accounting.accounts import ACCOUNT_CODES
from src.services.accounting_service import AccountingService
from src.services.balance_service import BalanceService
from src.workers import balance_snapshot_worker


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


def _build_parser_args(argv):
    return balance_snapshot_worker._build_parser().parse_args(argv)


def test_build_parser_defaults_to_yesterday():
    args = _build_parser_args([])
    assert args.as_of == date.today() - timedelta(days=1)


def test_build_parser_parses_explicit_date():
    args = _build_parser_args(["--as-of", "2026-01-15"])
    assert args.as_of == date(2026, 1, 15)


def test_build_parser_as_of_empty_string_falls_back_to_yesterday():
    """--as-of "" exercises the `type=` lambda's own `else` branch (date.today()
    - timedelta(days=1)), which is distinct from argparse's top-level `default=`
    kwarg used when the flag is omitted entirely (see the test above). Both
    must independently resolve to "yesterday"."""
    args = _build_parser_args(["--as-of", ""])
    assert args.as_of == date.today() - timedelta(days=1)


@pytest.mark.asyncio
async def test_main_creates_snapshot_for_every_account(db_session, monkeypatch, seed_ledger_accounts):
    _patch_session(monkeypatch, balance_snapshot_worker, db_session)

    # Post a real balanced journal entry so at least one account has a
    # non-zero balance to snapshot -- exercises BalanceService.create_snapshot's
    # real aggregation query, not just an empty-ledger no-op path.
    accounting = AccountingService(db_session)
    result = await accounting.record_down_payment(order_id=1, amount=Decimal("500.00"))
    assert result.created is True

    as_of = date.today()
    await balance_snapshot_worker.main(["--as-of", as_of.isoformat()])

    rows = (await db_session.execute(select(LedgerAccountBalance))).scalars().all()

    # One snapshot per account in ACCOUNT_CODES was attempted/created.
    assert len(rows) == len(set(ACCOUNT_CODES.values()))

    # Sanity: the cash account's persisted snapshot matches BalanceService's
    # own independently-computed balance for the same date (real aggregation
    # query, not a mocked return value).
    balance_service = BalanceService(db_session)
    cash_balance = await balance_service.get_account_balance(ACCOUNT_CODES["cash"], as_of=as_of)
    cash_account_id = (
        await db_session.execute(select(LedgerAccountBalance.account_id).where(LedgerAccountBalance.debit_balance == Decimal("500.00")))
    ).scalar_one()
    cash_snapshot = next(row for row in rows if row.account_id == cash_account_id)
    assert cash_snapshot.debit_balance == Decimal(str(cash_balance["debit_total"]))
    assert cash_snapshot.credit_balance == Decimal(str(cash_balance["credit_total"]))


@pytest.mark.asyncio
async def test_main_continues_after_one_account_snapshot_fails(db_session, monkeypatch, seed_ledger_accounts, caplog):
    """A single account's create_snapshot() raising must not abort the whole
    run -- the worker wraps each account in try/except so one bad account
    doesn't block snapshotting the rest (and still commits at the end)."""
    _patch_session(monkeypatch, balance_snapshot_worker, db_session)

    real_create_snapshot = BalanceService.create_snapshot
    failing_code = ACCOUNT_CODES["cash"]
    call_log: list[str] = []

    async def _flaky_create_snapshot(self, account_code, snapshot_date, currency=None):
        call_log.append(account_code)
        if account_code == failing_code:
            raise RuntimeError("simulated snapshot failure")
        return await real_create_snapshot(self, account_code, snapshot_date, currency)

    monkeypatch.setattr(BalanceService, "create_snapshot", _flaky_create_snapshot)

    as_of = date.today()
    await balance_snapshot_worker.main(["--as-of", as_of.isoformat()])

    # Every account was attempted, including the one that raised.
    assert failing_code in call_log
    assert len(call_log) == len(set(ACCOUNT_CODES.values()))

    # Every OTHER account still got a persisted, committed snapshot.
    rows = (await db_session.execute(select(LedgerAccountBalance))).scalars().all()
    assert len(rows) == len(set(ACCOUNT_CODES.values())) - 1
