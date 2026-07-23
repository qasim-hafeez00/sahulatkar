from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import fakeredis.aioredis
import pytest
from sqlalchemy import select

from sk_shared.models.ledger import LateFeeCharityAllocation
from sk_shared.models.payment import Installment, Loan
from sk_shared.redis_client import RedisClient
from src.billing.billing_sweep import BillingSweepService
from src.config import settings
from src.workers import billing_sweep_worker


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


def _install_fake_redis(monkeypatch) -> RedisClient:
    """Replace get_redis_client() with a real RedisClient wrapping fakeredis,
    so BillingSweepService's actual lock-acquire/release Redis commands run
    against a real (in-memory) Redis protocol implementation instead of a
    hand-rolled stub."""
    client = RedisClient(fakeredis.aioredis.FakeRedis())
    monkeypatch.setattr(billing_sweep_worker, "get_redis_client", lambda url, db=0: client)
    return client


def _make_loan(loan_number: str, user_id: int) -> Loan:
    return Loan(
        order_id=user_id,
        user_id=user_id,
        loan_number=loan_number,
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


def test_build_parser_defaults():
    parser = billing_sweep_worker._build_parser()
    args = parser.parse_args([])
    assert args.as_of == date.today()
    assert args.batch_size == 500
    assert args.dry_run is False


def test_build_parser_parses_explicit_args():
    parser = billing_sweep_worker._build_parser()
    args = parser.parse_args(["--as-of", "2026-01-15", "--batch-size", "50", "--dry-run"])
    assert args.as_of == date(2026, 1, 15)
    assert args.batch_size == 50
    assert args.dry_run is True


@pytest.mark.asyncio
async def test_main_passes_cli_args_through_to_service(db_session, monkeypatch):
    """The worker is a thin CLI wrapper; verify it forwards as_of/batch_size/
    dry_run to BillingSweepService.execute_sweep unchanged."""
    _patch_session(monkeypatch, billing_sweep_worker, db_session)
    _install_fake_redis(monkeypatch)

    captured: dict[str, object] = {}

    async def _fake_execute_sweep(self, as_of=None, batch_size=500, dry_run=False):
        captured["as_of"] = as_of
        captured["batch_size"] = batch_size
        captured["dry_run"] = dry_run
        return {"total": 0, "success": 0, "failed": 0, "already_paid": 0, "newly_overdue": 0, "late_fees_applied": 0}

    monkeypatch.setattr(BillingSweepService, "execute_sweep", _fake_execute_sweep)

    await billing_sweep_worker.main(["--as-of", "2026-02-01", "--batch-size", "25", "--dry-run"])

    assert captured == {"as_of": date(2026, 2, 1), "batch_size": 25, "dry_run": True}


@pytest.mark.asyncio
async def test_main_builds_redis_client_from_configured_url_and_db(db_session, monkeypatch):
    """main() must forward settings.redis_url/settings.redis_db unchanged to
    get_redis_client -- not drop either argument or pass None."""
    _patch_session(monkeypatch, billing_sweep_worker, db_session)

    captured: dict[str, object] = {}

    def _fake_get_redis_client(url, db=0):
        captured["url"] = url
        captured["db"] = db
        return RedisClient(fakeredis.aioredis.FakeRedis())

    monkeypatch.setattr(billing_sweep_worker, "get_redis_client", _fake_get_redis_client)

    async def _fake_execute_sweep(self, as_of=None, batch_size=500, dry_run=False):
        return {"total": 0, "success": 0, "failed": 0, "already_paid": 0, "newly_overdue": 0, "late_fees_applied": 0}

    monkeypatch.setattr(BillingSweepService, "execute_sweep", _fake_execute_sweep)

    await billing_sweep_worker.main([])

    assert captured == {"url": settings.redis_url, "db": settings.redis_db}


@pytest.mark.asyncio
async def test_main_dry_run_detects_overdue_but_skips_late_fee(db_session, monkeypatch, seed_ledger_accounts):
    """dry_run must genuinely make no DB modifications: newly_overdue is still
    detected/reported, but no late-fee journal entry/allocation is created."""
    _patch_session(monkeypatch, billing_sweep_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)

    loan = _make_loan("L-DRY", 701)
    db_session.add(loan)
    await db_session.flush()
    old_due = date.today() - timedelta(days=5)
    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=1,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=old_due,
        status="pending",
        retry_count=0,
    )
    db_session.add(inst)
    await db_session.commit()

    await billing_sweep_worker.main(["--dry-run"])

    await db_session.refresh(inst)
    assert inst.status == "pending"  # ledger never writes to the installments table directly

    allocations = (await db_session.execute(select(LateFeeCharityAllocation))).scalars().all()
    assert allocations == []  # dry-run's documented "no database modifications" contract

    # Lock must still be released after a dry-run so the next scheduled sweep isn't blocked.
    assert await redis_client.get(BillingSweepService.LOCK_KEY) is None


@pytest.mark.asyncio
async def test_main_normal_run_applies_late_fee_and_releases_lock(db_session, monkeypatch, seed_ledger_accounts):
    _patch_session(monkeypatch, billing_sweep_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)

    loan = _make_loan("L-REAL", 702)
    db_session.add(loan)
    await db_session.flush()
    old_due = date.today() - timedelta(days=5)
    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=1,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=old_due,
        status="pending",
        retry_count=0,
    )
    db_session.add(inst)
    await db_session.commit()

    await billing_sweep_worker.main([])

    allocation = (
        await db_session.execute(
            select(LateFeeCharityAllocation).where(LateFeeCharityAllocation.installment_id == inst.id)
        )
    ).scalar_one()
    assert Decimal(str(allocation.late_fee_amount)) == Decimal("150.00")

    assert await redis_client.get(BillingSweepService.LOCK_KEY) is None


@pytest.mark.asyncio
async def test_main_skips_run_when_lock_already_held(db_session, monkeypatch, seed_ledger_accounts):
    """Simulates a concurrent sweep already holding the distributed lock;
    this run must be a no-op (no late fees applied) rather than racing it."""
    _patch_session(monkeypatch, billing_sweep_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)
    await redis_client.redis.set(BillingSweepService.LOCK_KEY, "other-owner", nx=True)

    loan = _make_loan("L-LOCKED", 703)
    db_session.add(loan)
    await db_session.flush()
    inst = Installment(
        loan_id=loan.id,
        user_id=loan.user_id,
        installment_number=1,
        principal_portion=2500,
        profit_portion=100,
        total_amount=2600,
        due_date=date.today() - timedelta(days=5),
        status="pending",
        retry_count=0,
    )
    db_session.add(inst)
    await db_session.commit()

    await billing_sweep_worker.main([])

    allocations = (await db_session.execute(select(LateFeeCharityAllocation))).scalars().all()
    assert allocations == []

    # The lock we pre-seeded (owned by "other-owner") must be left untouched.
    assert await redis_client.get(BillingSweepService.LOCK_KEY) == "other-owner"


@pytest.mark.asyncio
async def test_main_closes_redis_client_even_if_sweep_raises(db_session, monkeypatch):
    """Regression test for a resource leak: main() used to call
    redis_client.close() only after the `async with SessionLocal()` block
    completed successfully, so any exception out of execute_sweep() (or the
    block itself) leaked the Redis connection pool for the life of the
    process. Fixed by wrapping the block in try/finally."""
    _patch_session(monkeypatch, billing_sweep_worker, db_session)
    redis_client = _install_fake_redis(monkeypatch)

    async def _boom(self, as_of=None, batch_size=500, dry_run=False):
        raise RuntimeError("simulated sweep failure")

    monkeypatch.setattr(BillingSweepService, "execute_sweep", _boom)

    close_calls = {"n": 0}
    real_close = redis_client.close

    async def _tracking_close():
        close_calls["n"] += 1
        await real_close()

    monkeypatch.setattr(redis_client, "close", _tracking_close)

    with pytest.raises(RuntimeError, match="simulated sweep failure"):
        await billing_sweep_worker.main([])

    assert close_calls["n"] == 1
