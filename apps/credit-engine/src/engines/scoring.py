from __future__ import annotations

from dataclasses import dataclass

from src.policy.rule_policy import RulePolicy, ScoreBin


@dataclass
class ScoreResult:
    score: float
    band: str
    base_limit: float
    down_payment_pct: float
    model_version: str
    identity_contribution: float
    alt_data_contribution: float


class ScoringEngine:
    """WOE-style points scorecard: identity + alt-data signals are each binned per
    RulePolicy.identity_score_bins / alt_data_score_bins, and the matched bins' points sum
    into a 0-900 score, banded A-F. This is the honest cold-start approach (see the plan's
    model-weights research — there is no defensible pretrained credit model for first-time
    Pakistani BNPL borrowers), not a placeholder for a "real" model. It's additive by
    construction, which is what makes ExplanationBuilder's per-factor contributions exact
    rather than approximated.

    Swap point for Phase 3.5+: once ~3-6 months of repayment outcomes exist, bin cut points
    and point values can be refit with WOE/IV against actual defaults (optbinning), and
    eventually a trained LightGBM/XGBoost model (via ONNX Runtime) replaces the body of
    `score()` entirely behind this same ScoringEngine interface — callers never change.
    """

    def __init__(self, policy: RulePolicy, model_version: str = "scorecard-v1") -> None:
        self.policy = policy
        self.model_version = model_version

    def score(self, identity_score: float, alt_data_score: float) -> ScoreResult:
        identity_contribution = self._bin_points(self.policy.identity_score_bins, identity_score)
        alt_data_contribution = self._bin_points(self.policy.alt_data_score_bins, alt_data_score)
        raw = identity_contribution + alt_data_contribution
        score = min(max(raw, 0.0), self.policy.max_raw_score)

        band = "F"
        for candidate_band, cutoff in sorted(
            self.policy.score_band_cutoffs.items(), key=lambda item: item[1], reverse=True
        ):
            if score >= cutoff:
                band = candidate_band
                break

        base_limit = self.policy.band_base_limits.get(band, 0.0)
        down_payment_pct = self.policy.band_down_payment_pct.get(band, 0.0)

        return ScoreResult(
            score=score,
            band=band,
            base_limit=base_limit,
            down_payment_pct=down_payment_pct,
            model_version=self.model_version,
            identity_contribution=round(identity_contribution, 2),
            alt_data_contribution=round(alt_data_contribution, 2),
        )

    @staticmethod
    def _bin_points(bins: list[ScoreBin], value: float) -> float:
        for score_bin in bins:
            if score_bin.min_score <= value < score_bin.max_score:
                return score_bin.points
        # Value falls above every configured bin's range (inputs are already clamped to
        # 0-100 upstream, so this is defensive, not the expected path) — treat as top band.
        return bins[-1].points if bins else 0.0
