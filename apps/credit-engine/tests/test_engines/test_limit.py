from datetime import date, timedelta

import pytest

from sk_shared.models.payment import Installment, Loan
from src.engines.limit import LimitEngine
from src.policy.rule_policy import RulePolicy


async def _seed_loan(
    db_session,
    user,
    *,
    order_id: int,
    status: str = "fully_paid",
    late_fee_total: float = 0.0,
    installment_status: str = "paid",
    installment_late_fee: float = 0.0,
) -> None:
    """A completed BNPL loan cycle for LimitEngine.has_repayment_track_record tests. Principal/
    profit figures are arbitrary but internally consistent; only status/late_fee fields matter
    to the graduation rule itself."""
    loan = Loan(
        order_id=order_id,
        user_id=user.id,
        loan_number=f"SAK-LOAN-TEST-{order_id}",
        principal_amount=4000.0,
        profit_amount=200.0,
        total_repayable=4200.0,
        down_payment_amount=1000.0,
        balance_financed=3200.0,
        profit_rate_pct=5.0,
        plan_type="pay_in_4",
        installment_count=4,
        installment_amount=800.0,
        status=status,
        total_paid=4200.0 if status == "fully_paid" else 0.0,
        total_outstanding=0.0 if status == "fully_paid" else 3200.0,
        late_fee_total=late_fee_total,
    )
    db_session.add(loan)
    await db_session.flush()
    for i in range(1, 5):
        db_session.add(Installment(
            loan_id=loan.id,
            user_id=user.id,
            installment_number=i,
            is_down_payment=False,
            principal_portion=750.0,
            profit_portion=50.0,
            total_amount=800.0,
            due_date=date.today() - timedelta(days=30 * (5 - i)),
            status=installment_status,
            paid_amount=800.0 if installment_status == "paid" else 0.0,
            days_overdue=0,
            late_fee_amount=installment_late_fee,
            late_fee_waived=False,
            retry_count=0,
        ))
    await db_session.commit()


def test_prohibited_category_blocks_overlay():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    result = engine.apply_category_overlay(10000.0, 25.0, "Alcohol")
    assert result.blocked is True
    assert result.reason == "Prohibited category"
    assert result.limit == 0.0


def test_high_risk_category_reduces_limit_and_bumps_down_payment():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    result = engine.apply_category_overlay(10000.0, 25.0, "gold jewelry")
    assert result.blocked is False
    assert result.limit == 4000.0  # 10000 * 0.40
    assert result.down_payment_pct == 30.0  # 25 + 5 bump
    assert "high_risk_category" in result.flags


def test_general_category_applies_no_adjustment():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    result = engine.apply_category_overlay(10000.0, 25.0, "general")
    assert result.limit == 10000.0
    assert result.down_payment_pct == 25.0
    assert result.flags == []


def test_unknown_category_uses_default_multiplier():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    result = engine.apply_category_overlay(10000.0, 25.0, "furniture")
    assert result.limit == 10000.0 * RulePolicy().default_category_multiplier


def test_cold_start_cap_applies_only_on_first_order():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert engine.apply_cold_start_cap(20000.0, "A", is_first_order=True) == 8000.0
    assert engine.apply_cold_start_cap(20000.0, "A", is_first_order=False) == 20000.0


def test_cold_start_cap_is_a_ceiling_not_a_floor():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert engine.apply_cold_start_cap(3000.0, "A", is_first_order=True) == 3000.0


def test_cold_start_cap_applies_when_data_sparse_even_on_repeat_orders():
    # A score built with zero device/IP/bank-statement evidence is capped the same way a
    # genuine first order is, regardless of the caller-supplied is_first_order flag — see
    # Phase 6's cold-start inversion fix.
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert engine.apply_cold_start_cap(20000.0, "A", is_first_order=False, data_sparse=True) == 8000.0


def test_cold_start_cap_not_applied_when_neither_first_order_nor_data_sparse():
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert engine.apply_cold_start_cap(20000.0, "A", is_first_order=False, data_sparse=False) == 20000.0


def test_clamp_to_maximum():
    engine = LimitEngine(RulePolicy(), maximum_limit=5000.0)
    assert engine.clamp_to_maximum(10000.0) == 5000.0
    assert engine.clamp_to_maximum(1000.0) == 1000.0


@pytest.mark.asyncio
async def test_portfolio_concentration_blocks_when_exposure_exceeds_maximum(db_session, approved_user):
    engine = LimitEngine(RulePolicy(), maximum_limit=10000.0)
    result = await engine.check_portfolio_concentration(
        db_session, str(approved_user.uuid), requested_amount=15000.0
    )
    assert result.blocked is True
    assert "portfolio_limit_exceeded" in result.flags


@pytest.mark.asyncio
async def test_portfolio_concentration_flags_high_utilization(db_session, approved_user):
    engine = LimitEngine(RulePolicy(), maximum_limit=10000.0)
    result = await engine.check_portfolio_concentration(
        db_session, str(approved_user.uuid), requested_amount=8500.0
    )
    assert result.blocked is False
    assert "high_utilization" in result.flags


# ── has_repayment_track_record (Phase 6 cold-start graduation bugfix) ──────────────────────

@pytest.mark.asyncio
async def test_repayment_track_record_false_for_applicant_with_no_loan_history(db_session, approved_user):
    """(a) A brand-new applicant with zero completed loans has no track record to graduate
    on — existing cold-start behavior is preserved for them."""
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, str(approved_user.uuid)) is False


@pytest.mark.asyncio
async def test_repayment_track_record_false_below_the_graduation_threshold(db_session, approved_user):
    # Two clean, fully-repaid loans is real history, but RulePolicy.graduation_min_repaid_loans
    # defaults to 3 — a single or a pair of completed cycles isn't yet the repeated pattern the
    # rule requires.
    await _seed_loan(db_session, approved_user, order_id=1)
    await _seed_loan(db_session, approved_user, order_id=2)

    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, str(approved_user.uuid)) is False


@pytest.mark.asyncio
async def test_repayment_track_record_true_for_strong_clean_history(db_session, approved_user):
    """(b) At (or above) the threshold, with every loan fully repaid and every installment
    clean, the applicant graduates."""
    await _seed_loan(db_session, approved_user, order_id=1)
    await _seed_loan(db_session, approved_user, order_id=2)
    await _seed_loan(db_session, approved_user, order_id=3)

    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, str(approved_user.uuid)) is True


@pytest.mark.asyncio
async def test_repayment_track_record_false_when_any_loan_carries_a_late_fee(db_session, approved_user):
    """(c) Mixed history: three fully-paid loans, but one of them accrued a late fee at some
    point. ANY negative signal disqualifies the whole applicant, not just that one loan."""
    await _seed_loan(db_session, approved_user, order_id=1)
    await _seed_loan(db_session, approved_user, order_id=2)
    await _seed_loan(db_session, approved_user, order_id=3, late_fee_total=50.0, installment_late_fee=50.0)

    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, str(approved_user.uuid)) is False


@pytest.mark.asyncio
async def test_repayment_track_record_false_when_an_installment_was_ever_overdue(db_session, approved_user):
    # Loan-level late_fee_total can be 0 (e.g. a late fee was waived) while an installment still
    # carries an "overdue" status from its history — checked independently so this can't slip
    # through.
    await _seed_loan(db_session, approved_user, order_id=1)
    await _seed_loan(db_session, approved_user, order_id=2)
    await _seed_loan(db_session, approved_user, order_id=3, installment_status="overdue")

    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, str(approved_user.uuid)) is False


@pytest.mark.asyncio
async def test_repayment_track_record_ignores_loans_that_are_not_fully_paid(db_session, approved_user):
    # An active/in-progress loan (however clean so far) doesn't count toward the threshold —
    # only completed cycles do.
    await _seed_loan(db_session, approved_user, order_id=1)
    await _seed_loan(db_session, approved_user, order_id=2)
    await _seed_loan(db_session, approved_user, order_id=3, status="active", installment_status="pending")

    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, str(approved_user.uuid)) is False


@pytest.mark.asyncio
async def test_repayment_track_record_invalid_user_id_returns_false(db_session):
    engine = LimitEngine(RulePolicy(), maximum_limit=500000.0)
    assert await engine.has_repayment_track_record(db_session, "not-a-uuid") is False
