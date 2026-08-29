from __future__ import annotations

"""
Regression tests for src/workers/charity_disbursement_worker.py.

Item 6 from the original audit brief: charity disbursement
(CharityService.process_charity_allocation) had no automated schedule --
only a manual admin-triggered API path
(apps/ledger-service/src/api/v1/finance.py's charity disbursement endpoint).
process_charity_allocation() itself was already a complete auto-disbursement
pipeline (nisab check, GL balance pre-check, its own Redis lock -- see
tests/test_charity_lock.py), so the only missing piece was a periodic entry
point to invoke it, mirroring the exact shape
src/workers/billing_sweep_worker.py already uses for BillingSweepService:
argparse CLI -> fresh DB session -> real Redis client (closed in `finally`).
These tests follow tests/test_billing_sweep_worker.py's own patterns.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import fakeredis.aioredis
import pytest
from sqlalchemy import select

from sk_shared.models.ledger import LateFeeCharityAllocation
from sk_shared.models.payment import Installment, Loan
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.services.accounting_service import AccountingService
from src.services.charity_service import CharityService
from src.workers import charity_disbursement_worker


class _SessionContextManager:
    """Wraps an already-open AsyncSession so `async with SessionLocal() as
    session:` (as used by main()) yields the test's real db_session instead
    of opening a connection to the production database configured in
    src.core.database.SessionLocal."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _patch_session(monkeypatch, module, session) -> None:
    monkeypatch.setattr(module, "SessionLocal", lambda: _SessionContextManager(session))


def _install_fake_redis(monkeypatch) -> RedisClient:
    client = RedisClient(fakeredis.aioredis.FakeRedis())
    monkeypatch.setattr(charity_disbursement_worker, "get_redis_client", lambda url, db=0: client)
    return client


def test_build_parser_defaults():
    parser = charity_disbursement_worker._build_parser()
    args = parser.parse_args([])
    assert args.payment_reference is None
    assert args.receipt_s3 is None


def test_build_parser_parses_explicit_args():
    parser = charity_disbursement_worker._build_parser()
    args = parser.parse_args(["--payment-reference", "PAY-REF-1", "--receipt-s3", "s3://bucket/receipt.pdf"])
    assert args.payment_reference == "PAY-REF-1"
    assert args.receipt_s3 == "s3://bucket/receipt.pdf"


@pytest.mark.asyncio
async def test_main_passes_cli_args_through_to_service(db_session, monkeypatch):
    """The worker is a thin CLI wrapper; verify it forwards payment_reference/
    receipt_s3 to CharityService.process_charity_allocation unchanged."""
    _patch_session(monkeypatch, charity_disbursement_worker, db_session)
    _install_fake_redis(monkeypatch)

    captured: dict[str, object] = {}

    async def _fake_process_charity_allocation(self, payment_reference=None, receipt_s3=None):
        captured["payment_reference"] = payment_reference
        captured["receipt_s3"] = receipt_s3
        return {"status": "no_pending", "disbursed_count": 0, "total_amount": 0.0}

    monkeypatch.setattr(CharityService, "process_charity_allocation", _fake_process_charity_allocation)

    await charity_disbursement_worker.main(["--payment-reference", "PAY-REF-2", "--receipt-s3", "s3://x/r.pdf"])

    assert captured == {"payment_reference": "PAY-REF-2", "receipt_s3": "s3://x/r.pdf"}


@pytest.mark.asyncio
async def test_main_builds_redis_client_from_configured_url_and_db(db_session, monkeypatch):
    """main() must forward settings.redis_url/settings.redis_db unchanged to
    get_redis_client -- not drop either argument or pass None."""
    _patch_session(monkeypatch, charity_disbursement_worker, db_session)

    captured: dict[str, object] = {}

    def _fake_get_redis_client(url, db=0):
        captured["url"] = url
        captured["db"] = db
        return RedisClient(fakeredis.aioredis.FakeRedis())

    monkeypatch.setattr(charity_disbursement_worker, "get_redis_client", _fake_get_redis_client)

    async def _fake_process_charity_allocation(self, payment_reference=None, receipt_s3=None):
        return {"status": "no_pending", "disbursed_count": 0, "total_amount": 0.0}

    monkeypatch.setattr(CharityService, "process_charity_allocation", _fake_process_charity_allocation)

    await charity_disbursement_worker.main([])

    assert captured == {"url": settings.redis_url, "db": settings.redis_db}


@pytest.mark.asyncio
async def test_main_disburses_pending_allocation_and_releases_lock(db_session, monkeypatch, seed_ledger_accounts):
    """End-to-end happy path: a pending, sufficiently-old charity allocation
    (with GL funds already posted via record_late_fee) gets disbursed by a
    single worker run, and the distributed lock is released afterward."""
    _patch_session(monkeypatch, charity_disbursement_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)
    # Keep the nisab threshold from swallowing a small test late-fee amount.
    monkeypatch.setattr(settings, "shariah_nisab_pkr", 1.0)

    loan = Loan(
        order_id=601,
        user_id=601,
        loan_number="L-601",
        principal_amount=10000,
        profit_amount=400,
        total_repayable=10400,
        down_payment_amount=2600,
        balance_financed=7800,
        profit_rate_pct=4,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=2600,
    )
    db_session.add(loan)
    await db_session.flush()
    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=1,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=date.today(),
        status="overdue",
    )
    db_session.add(inst)
    await db_session.commit()

    accounting = AccountingService(db_session)
    await accounting.record_late_fee(inst.id, Decimal("100.00"))

    allocation = (
        await db_session.execute(
            select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
        )
    ).scalar_one()
    # Back-date the allocation well past the default min-age threshold so
    # get_pending_disbursements() picks it up regardless of config defaults.
    allocation.allocated_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db_session.commit()

    await charity_disbursement_worker.main([])

    await db_session.refresh(allocation)
    assert allocation.disbursed_at is not None
    assert await redis_client.get(CharityService.LOCK_KEY) is None


@pytest.mark.asyncio
async def test_main_skips_run_when_lock_already_held(db_session, monkeypatch, seed_ledger_accounts):
    """Simulates a concurrent disbursement run already holding the
    distributed lock; this run must be a no-op rather than racing it."""
    _patch_session(monkeypatch, charity_disbursement_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)
    await redis_client.redis.set(CharityService.LOCK_KEY, "other-owner", nx=True)

    await charity_disbursement_worker.main([])

    # The lock we pre-seeded (owned by "other-owner") must be left untouched.
    assert await redis_client.get(CharityService.LOCK_KEY) == "other-owner"


@pytest.mark.asyncio
async def test_main_closes_redis_client_even_if_sweep_raises(db_session, monkeypatch):
    """Mirrors billing_sweep_worker's resource-leak regression test:
    main() must call redis_client.close() even if
    process_charity_allocation() raises."""
    _patch_session(monkeypatch, charity_disbursement_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)

    async def _boom(self, payment_reference=None, receipt_s3=None):
        raise RuntimeError("simulated charity disbursement failure")

    monkeypatch.setattr(CharityService, "process_charity_allocation", _boom)

    close_calls = {"n": 0}
    real_close = redis_client.close

    async def _tracking_close():
        close_calls["n"] += 1
        await real_close()

    monkeypatch.setattr(redis_client, "close", _tracking_close)

    with pytest.raises(RuntimeError, match="simulated charity disbursement failure"):
        await charity_disbursement_worker.main([])

    assert close_calls["n"] == 1
