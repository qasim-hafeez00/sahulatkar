"""
Tests for src/workers/reminder_worker.py.

Phase 2: this worker had zero test coverage and, once exercised, turned out
to be completely broken — it imported a nonexistent sk_shared.models.payment.
InstallmentStatus enum and joined Installment straight to Order via a
nonexistent Installment.order_id column (Installment only has loan_id;
Order is reachable only via Loan). Both fire_installment_reminders() and
fire_overdue_reminders() would raise on the very first query. Fixed to join
through Loan and use the real plain-string status values ("pending",
"overdue") used everywhere else in this codebase, then covered here.
"""
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from sk_shared.models.auth import User
from sk_shared.models.notification import Notification
from sk_shared.models.order import Order
from sk_shared.models.payment import Installment, Loan
from sk_shared.redis_client import RedisClient

from src.workers import reminder_worker

pytestmark = pytest.mark.asyncio


async def _seed_installment(session, *, user_id: int, due_date: date, status: str) -> Installment:
    user = User(phone=f"+9230010{user_id:05d}", status="active")
    session.add(user)
    await session.flush()

    order = Order(
        user_id=user.id,
        product_id=None,
        status="down_payment_received",
        total_amount=Decimal("5200"),
        down_payment_amount=Decimal("1300"),
        product_description="Test item",
    )
    session.add(order)
    await session.flush()

    loan = Loan(
        order_id=order.id,
        user_id=user.id,
        loan_number=f"SAK-LOAN-{order.id:010d}",
        principal_amount=Decimal("5000"),
        profit_amount=Decimal("200"),
        total_repayable=Decimal("5200"),
        down_payment_amount=Decimal("1300"),
        balance_financed=Decimal("3900"),
        profit_rate_pct=Decimal("4"),
        plan_type="murabaha_installment",
        installment_count=4,
        installment_amount=Decimal("975"),
        status="active",
    )
    session.add(loan)
    await session.flush()

    installment = Installment(
        loan_id=loan.id,
        user_id=user.id,
        installment_number=1,
        is_down_payment=False,
        principal_portion=Decimal("925"),
        profit_portion=Decimal("50"),
        total_amount=Decimal("975"),
        due_date=due_date,
        status=status,
    )
    session.add(installment)
    await session.commit()
    await session.refresh(installment)
    return installment


@pytest.fixture(autouse=True)
def _patch_worker_infra(monkeypatch, db_session, redis_mock: RedisClient):
    """Point the worker's module-level `SessionLocal()` at the test's own
    session instead of a fresh one from the sessionmaker: a second aiosqlite
    ``:memory:`` connection off the same StaticPool-backed engine sees an
    empty database (each new connection gets its own private in-memory DB),
    so worker code must share the exact session object the test seeds
    through — mirroring how this service's FastAPI dependency overrides
    already share `db_session` rather than opening a second connection."""
    @asynccontextmanager
    async def _session_cm():
        yield db_session

    monkeypatch.setattr(reminder_worker, "SessionLocal", _session_cm)
    monkeypatch.setattr(reminder_worker, "get_redis_client", lambda *a, **k: redis_mock)


async def test_fire_installment_reminders_creates_notification_for_due_installment(db_session):
    due_date = (datetime.now(timezone.utc) + timedelta(days=3)).date()
    installment = await _seed_installment(db_session, user_id=1, due_date=due_date, status="pending")

    stats = await reminder_worker.fire_installment_reminders()

    assert stats["created"] == 1
    assert stats["errors"] == 0

    notification = await db_session.scalar(
        select(Notification).where(
            Notification.idempotency_key == f"reminder-d3-installment-{installment.id}-{due_date}"
        )
    )
    assert notification is not None
    assert notification.source_event == "billing.installment_due_d3"


async def test_fire_installment_reminders_is_idempotent(db_session):
    due_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    await _seed_installment(db_session, user_id=2, due_date=due_date, status="pending")

    first = await reminder_worker.fire_installment_reminders()
    second = await reminder_worker.fire_installment_reminders()

    assert first["created"] == 1
    # Re-running immediately finds the same installment due again — the
    # idempotency guard lives in NotificationService.create_notification,
    # which returns the existing row instead of erroring or duplicating.
    assert second["processed"] == 1


async def test_fire_installment_reminders_ignores_installments_not_yet_due(db_session):
    far_future = (datetime.now(timezone.utc) + timedelta(days=30)).date()
    await _seed_installment(db_session, user_id=3, due_date=far_future, status="pending")

    stats = await reminder_worker.fire_installment_reminders()

    assert stats["processed"] == 0
    assert stats["created"] == 0


async def test_fire_overdue_reminders_creates_notification_for_overdue_installment(db_session):
    overdue_date = (datetime.now(timezone.utc) - timedelta(days=7)).date()
    installment = await _seed_installment(db_session, user_id=4, due_date=overdue_date, status="overdue")

    stats = await reminder_worker.fire_overdue_reminders()

    assert stats["created"] == 1
    notification = await db_session.scalar(
        select(Notification).where(
            Notification.idempotency_key.like(f"overdue-d7-installment-{installment.id}-%")
        )
    )
    assert notification is not None
    assert notification.source_event == "billing.installment_overdue_d7"


async def test_fire_overdue_reminders_ignores_paid_installments(db_session):
    overdue_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    await _seed_installment(db_session, user_id=5, due_date=overdue_date, status="paid")

    stats = await reminder_worker.fire_overdue_reminders()

    assert stats["processed"] == 0
