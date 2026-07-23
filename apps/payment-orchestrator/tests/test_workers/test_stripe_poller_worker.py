"""
Tests for StripePoller (src/services/stripe_poller.py) and
StripePollerWorker (src/workers/stripe_poller_worker.py).

This worker runs live in production, polling Stripe Issuing for VCN status
as a fallback in case a cancellation webhook was delayed or lost. It had 0%
test coverage before this file.

Bug found and fixed while writing these tests: StripePoller called
``self.stripe.get_card(issuer_card_id)``, but StripeIssuingAdapter never
defined a `get_card` method. Every poll cycle, for every active VCN, this
raised AttributeError — silently swallowed by the per-card try/except in
`poll_active_vcns`, so the poller never actually detected a single
Stripe-side cancellation in production. Fixed by adding
`StripeIssuingAdapter.get_card` (see src/adapters/stripe_issuing.py) which
calls `stripe.issuing.Card.retrieve`. These tests exercise the real
(now-fixed) adapter method rather than mocking `get_card` itself, so they
would have caught the original bug (AttributeError bubbling out of
`self.stripe.get_card(...)`).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from sk_shared.models.payment import VirtualCard
from sqlalchemy import select

from src.config import settings
from src.services.stripe_poller import StripePoller
from src.workers.stripe_poller_worker import StripePollerWorker
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def _create_vcn(session, *, status: str, issuer_card_id: str, order_id: int | None = None) -> VirtualCard:
    now = datetime.now(timezone.utc)
    if order_id is None:
        order_id = int(now.timestamp() * 1_000_000) % 1_000_000_000
    card = VirtualCard(
        order_id=order_id,
        user_id=555,
        issuer="stripe",
        issuer_card_id=issuer_card_id,
        masked_number="**** **** **** 4242",
        card_expiry=(now + timedelta(days=365)).date(),
        authorized_amount=Decimal("5200.00"),
        loaded_amount=Decimal("5200.00"),
        mcc_lock="retail",
        merchant_lock=None,
        charged_amount=Decimal("0.00"),
        is_used=False,
        status=status,
        issued_at=now,
        expires_at=now + timedelta(hours=24),
        encrypted_pan=b"enc-pan",
        encrypted_cvv=b"enc-cvv",
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return card


# ── StripePoller.poll_active_vcns — success paths ────────────────────────────


async def test_poll_marks_card_expired_when_stripe_reports_canceled(db_session):
    """A VCN that Stripe reports as 'canceled' must be flipped to 'expired' locally."""
    card = await _create_vcn(db_session, status="active", issuer_card_id="ic_canceled_1")

    fake_stripe_card = MagicMock(status="canceled")
    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.return_value = fake_stripe_card
        poller = StripePoller(db_session)
        await poller.poll_active_vcns()

    refreshed = await db_session.get(VirtualCard, card.id)
    assert refreshed.status == "expired"
    mock_stripe.issuing.Card.retrieve.assert_called_once_with("ic_canceled_1")


async def test_poll_leaves_card_active_when_stripe_reports_active(db_session):
    """A VCN that Stripe still reports as 'active' must not be touched."""
    card = await _create_vcn(db_session, status="active", issuer_card_id="ic_still_active")

    fake_stripe_card = MagicMock(status="active")
    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.return_value = fake_stripe_card
        poller = StripePoller(db_session)
        await poller.poll_active_vcns()

    refreshed = await db_session.get(VirtualCard, card.id)
    assert refreshed.status == "active"


async def test_poll_only_queries_active_cards(db_session):
    """Cards not in 'active' status must never be polled or mutated."""
    voided = await _create_vcn(db_session, status="voided", issuer_card_id="ic_voided_1")
    expired = await _create_vcn(db_session, status="expired", issuer_card_id="ic_expired_1")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.return_value = MagicMock(status="canceled")
        poller = StripePoller(db_session)
        await poller.poll_active_vcns()

    assert mock_stripe.issuing.Card.retrieve.call_count == 0
    r_voided = await db_session.get(VirtualCard, voided.id)
    r_expired = await db_session.get(VirtualCard, expired.id)
    assert r_voided.status == "voided"
    assert r_expired.status == "expired"


async def test_poll_already_expired_active_row_is_untouched_if_still_active_on_stripe(db_session):
    """Cards already 'active' with Stripe status not 'canceled' stay untouched (no spurious writes)."""
    card = await _create_vcn(db_session, status="active", issuer_card_id="ic_inactive_not_canceled")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        # Stripe can report other non-canceled statuses (e.g. "inactive") —
        # only "canceled" should trigger a local status flip.
        mock_stripe.issuing.Card.retrieve.return_value = MagicMock(status="inactive")
        poller = StripePoller(db_session)
        await poller.poll_active_vcns()

    refreshed = await db_session.get(VirtualCard, card.id)
    assert refreshed.status == "active"


# ── StripePoller.poll_active_vcns — Stripe API error path ────────────────────


async def test_poll_handles_stripe_api_error_for_one_card_without_crashing(db_session):
    """
    A Stripe API error on one card must be logged and swallowed, not raised —
    and must not prevent other cards in the same sweep from being processed.
    """
    failing = await _create_vcn(db_session, status="active", issuer_card_id="ic_boom")
    healthy = await _create_vcn(db_session, status="active", issuer_card_id="ic_ok")

    def _retrieve_side_effect(issuer_card_id):
        if issuer_card_id == "ic_boom":
            raise Exception("Stripe API timeout")
        return MagicMock(status="canceled")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.side_effect = _retrieve_side_effect
        poller = StripePoller(db_session)
        # Must not raise — errors for individual cards are caught per-card.
        await poller.poll_active_vcns()

    r_failing = await db_session.get(VirtualCard, failing.id)
    r_healthy = await db_session.get(VirtualCard, healthy.id)
    # The card whose Stripe lookup failed must be left untouched (no partial update).
    assert r_failing.status == "active"
    # The other card in the same sweep must still be processed correctly.
    assert r_healthy.status == "expired"
    assert mock_stripe.issuing.Card.retrieve.call_count == 2


async def test_poll_logs_error_for_failing_card(db_session, caplog):
    await _create_vcn(db_session, status="active", issuer_card_id="ic_error_logged")

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.side_effect = Exception("network unreachable")
        with caplog.at_level("ERROR"):
            poller = StripePoller(db_session)
            await poller.poll_active_vcns()

    assert any("Error polling card" in r.message for r in caplog.records)


async def test_poll_no_active_cards_is_a_noop(db_session):
    """An empty sweep must not error and must not touch Stripe."""
    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        poller = StripePoller(db_session)
        await poller.poll_active_vcns()

    assert mock_stripe.issuing.Card.retrieve.call_count == 0


# ── StripePollerWorker.run() / stop() — worker loop resilience ───────────────


async def test_worker_stop_sets_flag_false():
    worker = StripePollerWorker()
    assert worker.is_running is True
    worker.stop()
    assert worker.is_running is False


async def test_worker_run_loop_survives_poller_exception_and_keeps_polling(monkeypatch):
    """
    If an entire poll cycle blows up (e.g. DB connection error, not just a
    single card's Stripe call), the outer worker loop must log and continue
    to the next interval rather than crashing the background task. This is
    the worker's only "retry" mechanism — there is no separate backoff/DLQ
    for this poller (unlike src/workers/vcn_issue_worker.py's DLQ_MAX_RETRIES
    path); it simply retries on the next VCN_STATUS_POLL_INTERVAL_SECONDS tick.
    """
    import src.workers.stripe_poller_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    call_count = {"poll": 0, "sleep": 0}
    sleep_seconds_seen = []

    async def _fake_poll_active_vcns(self):
        call_count["poll"] += 1
        raise RuntimeError("simulated DB outage")

    async def _fake_sleep(seconds):
        sleep_seconds_seen.append(seconds)
        call_count["sleep"] += 1
        # Stop the infinite loop after two iterations so the test terminates.
        if call_count["sleep"] >= 2:
            worker.is_running = False

    monkeypatch.setattr("src.services.stripe_poller.StripePoller.poll_active_vcns", _fake_poll_active_vcns)
    monkeypatch.setattr(module.asyncio, "sleep", _fake_sleep)

    worker = StripePollerWorker()
    # Must not raise despite poll_active_vcns always raising.
    await worker.run()

    assert call_count["poll"] == 2
    assert call_count["sleep"] == 2
    # Each sleep must use the configured poll interval, not a hardcoded or
    # missing value -- if this ever regressed to e.g. asyncio.sleep(None),
    # the real (unpatched) asyncio.sleep would raise TypeError on every
    # cycle in production.
    assert sleep_seconds_seen == [settings.VCN_STATUS_POLL_INTERVAL_SECONDS] * 2


async def test_worker_run_processes_real_vcn_end_to_end(monkeypatch):
    """
    End-to-end: worker.run() opens its own DB session (via SessionLocal),
    constructs a real StripePoller, and actually flips a canceled card's
    status — proving the full wiring (worker -> SessionLocal -> StripePoller
    -> StripeIssuingAdapter -> stripe API) works, not just the pieces in
    isolation.
    """
    import src.workers.stripe_poller_worker as module

    monkeypatch.setattr(module, "SessionLocal", TestingSessionLocal)

    async with TestingSessionLocal() as seed_db:
        card = await _create_vcn(seed_db, status="active", issuer_card_id="ic_e2e_canceled")
    card_id = card.id

    call_count = {"sleep": 0}

    async def _fake_sleep(seconds):
        call_count["sleep"] += 1
        worker.is_running = False  # run exactly one iteration

    monkeypatch.setattr(module.asyncio, "sleep", _fake_sleep)

    with patch("src.adapters.stripe_issuing.stripe") as mock_stripe:
        mock_stripe.issuing.Card.retrieve.return_value = MagicMock(status="canceled")
        worker = StripePollerWorker()
        await worker.run()

    assert call_count["sleep"] == 1
    # Fresh session (worker mutated the row via its own SessionLocal-backed
    # session) — refetch rather than reuse a session that may have a stale
    # identity-mapped copy (expire_on_commit=False on the test engine).
    async with TestingSessionLocal() as verify_db:
        refreshed = await verify_db.get(VirtualCard, card_id)
        assert refreshed.status == "expired"
