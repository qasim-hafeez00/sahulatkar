import pytest

from src.engines.limit import LimitEngine
from src.policy.rule_policy import RulePolicy


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
