
from src.engines.scoring import ScoringEngine
from src.policy.rule_policy import RulePolicy


def test_max_signals_hit_the_top_bin_of_each_scorecard_and_band_a():
    engine = ScoringEngine(RulePolicy())
    result = engine.score(identity_score=100.0, alt_data_score=100.0)
    assert result.identity_contribution == 750.0
    assert result.alt_data_contribution == 150.0
    assert result.score == 900.0
    assert result.band == "A"


def test_bin_lower_bound_is_inclusive_upper_bound_is_exclusive():
    engine = ScoringEngine(RulePolicy())
    # 39.9 stays in the [0, 40) bin; 40.0 exactly crosses into [40, 60).
    below = engine.score(identity_score=39.9, alt_data_score=0.0)
    at_boundary = engine.score(identity_score=40.0, alt_data_score=0.0)
    assert below.identity_contribution == 0.0
    assert at_boundary.identity_contribution == 200.0


def test_score_bands_at_default_policy_cutoffs():
    engine = ScoringEngine(RulePolicy())

    assert engine.score(identity_score=100.0, alt_data_score=100.0).band == "A"  # 900
    assert engine.score(identity_score=90.0, alt_data_score=0.0).band == "B"  # 750
    assert engine.score(identity_score=75.0, alt_data_score=0.0).band == "C"  # 650
    assert engine.score(identity_score=65.0, alt_data_score=80.0).band == "D"  # 450 + 120 = 570
    assert engine.score(identity_score=0.0, alt_data_score=0.0).band == "F"  # 0


def test_score_is_clamped_to_max_raw_score():
    engine = ScoringEngine(RulePolicy())
    result = engine.score(identity_score=1000.0, alt_data_score=1000.0)
    assert result.score == RulePolicy().max_raw_score


def test_contributions_are_the_matched_bins_points_not_a_continuous_slope():
    policy = RulePolicy()
    engine = ScoringEngine(policy)
    # Two scores in the same bin ([60, 75)) contribute identical points -- a WOE-style
    # scorecard is a step function, not a linear formula.
    lower = engine.score(identity_score=61.0, alt_data_score=0.0)
    upper = engine.score(identity_score=74.0, alt_data_score=0.0)
    assert lower.identity_contribution == upper.identity_contribution == 450.0


def test_contributions_sum_to_the_raw_score_before_clamping():
    policy = RulePolicy()
    engine = ScoringEngine(policy)
    result = engine.score(identity_score=65.0, alt_data_score=80.0)
    assert result.identity_contribution + result.alt_data_contribution == result.score


def test_band_base_limit_and_down_payment_come_from_policy():
    policy = RulePolicy()
    engine = ScoringEngine(policy)
    result = engine.score(identity_score=100.0, alt_data_score=100.0)
    assert result.base_limit == policy.band_base_limits["A"]
    assert result.down_payment_pct == policy.band_down_payment_pct["A"]


def test_custom_policy_bins_are_honored():
    policy = RulePolicy(identity_score_bins=[
        {"min_score": 0, "max_score": 100.01, "points": 999.0},
    ])
    engine = ScoringEngine(policy)
    result = engine.score(identity_score=1.0, alt_data_score=0.0)
    assert result.identity_contribution == 999.0
