from datetime import date

import pytest

from sk_shared.models.credit import BankStatementAnalysis
from src.engines.affordability import AffordabilityEngine


@pytest.mark.asyncio
async def test_no_bank_statement_falls_back_to_wallet_only(db_session, approved_user):
    engine = AffordabilityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid))

    assert result.wallet_activity_score == 55.0  # mock wallet score, unblended
    assert result.income_signal == "unknown"
    assert result.provider == "mock-jazzcash"
    assert "bank_data_unavailable" in result.flags


@pytest.mark.asyncio
async def test_healthy_bank_statement_blends_with_wallet_score(db_session, approved_user):
    db_session.add(BankStatementAnalysis(
        user_id=approved_user.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        avg_balance=15000.0,
        income_estimate=50000.0,
        expense_ratio=0.30,
        salary_detected=True,
        nsf_events=0,
    ))
    await db_session.commit()

    engine = AffordabilityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid))

    # bank_score = 50 + 20 (salary) + (1-0.30)*30 = 91; blended = 55*0.5 + 91*0.5
    assert result.wallet_activity_score == pytest.approx(73.0)
    assert result.income_signal == "stable"
    assert "salary_verified" in result.flags
    assert result.income_estimate == 50000.0
    assert result.debt_to_income_ratio == pytest.approx(0.30)


@pytest.mark.asyncio
async def test_high_expense_ratio_and_low_income_flag_weak_signal(db_session, approved_user):
    db_session.add(BankStatementAnalysis(
        user_id=approved_user.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        avg_balance=2000.0,
        income_estimate=20000.0,
        expense_ratio=0.60,
        salary_detected=False,
        nsf_events=1,
    ))
    await db_session.commit()

    engine = AffordabilityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid))

    # bank_score = 50 + 0 + (1-0.60)*30 - 1*5 = 57; blended = 55*0.5 + 57*0.5
    assert result.wallet_activity_score == pytest.approx(56.0)
    assert result.income_signal == "weak"
    assert "high_debt_to_income" in result.flags
    assert "income_below_minimum" in result.flags


@pytest.mark.asyncio
async def test_most_recent_statement_period_wins(db_session, approved_user):
    db_session.add(BankStatementAnalysis(
        user_id=approved_user.id,
        period_start=date(2025, 12, 1),
        period_end=date(2025, 12, 31),
        expense_ratio=0.80,
        salary_detected=False,
    ))
    db_session.add(BankStatementAnalysis(
        user_id=approved_user.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        expense_ratio=0.10,
        salary_detected=True,
    ))
    await db_session.commit()

    engine = AffordabilityEngine()
    result = await engine.evaluate(db_session, str(approved_user.uuid))

    assert result.debt_to_income_ratio == pytest.approx(0.10)
    assert result.income_signal == "stable"
