from __future__ import annotations

from dataclasses import dataclass

from sk_shared.credit_reason_codes import FlagCode
from src.engines.affordability import AffordabilityResult
from src.engines.identity import IdentityResult
from src.engines.scoring import ScoreResult


@dataclass
class ExplanationFactor:
    label: str
    contribution: float
    kind: str  # "positive" | "negative" | "neutral"


# Flags that, when present, surface as a zero-contribution negative factor in the
# explanation. Extend this as new engines add flags rather than growing a chain of ifs.
_NEGATIVE_FLAG_LABELS: dict[str, str] = {
    FlagCode.HIGH_RISK_CATEGORY: "Product category carries elevated risk — limit and down payment adjusted",
    FlagCode.HIGH_UTILIZATION: "Approaching total portfolio exposure limit",
    FlagCode.MANUAL_REVIEW_REQUIRED: "Elevated fraud risk signals — routed for manual review",
    FlagCode.HIGH_DEBT_TO_INCOME: "Bank statement shows a high expense-to-income ratio",
    FlagCode.BANK_DATA_UNAVAILABLE: "No bank statement data available — affordability partially estimated",
    FlagCode.INCOME_BELOW_MINIMUM: "Estimated income is below the minimum threshold",
    FlagCode.COLD_START_DATA_SPARSE: "No device, IP, or bank-statement evidence available — conservative cold-start limit applied",
}


class ExplanationBuilder:
    """Turns the engines' scores/flags into ranked, human-readable "approved/rejected
    because" reasons — no black-box decisions. Because ScoringEngine is an additive points
    model, each factor's `contribution` is the exact number of points it added, not an
    approximation; Phase 3's trained model will populate the same shape from SHAP values."""

    def build_approval(
        self,
        *,
        identity: IdentityResult,
        affordability: AffordabilityResult,
        scoring: ScoreResult,
        flags: list[str],
    ) -> dict:
        factors = [
            ExplanationFactor(
                label=f"Identity verification score {identity.score:.0f}/100 (NADRA/Shufti)",
                contribution=scoring.identity_contribution,
                kind="positive" if scoring.identity_contribution > 0 else "neutral",
            ),
            ExplanationFactor(
                label=(
                    f"Wallet/alt-data activity score {affordability.wallet_activity_score:.0f}/100 "
                    f"({affordability.income_signal} income signal)"
                ),
                contribution=scoring.alt_data_contribution,
                kind="positive" if scoring.alt_data_contribution > 0 else "neutral",
            ),
        ]
        for flag, label in _NEGATIVE_FLAG_LABELS.items():
            if flag in flags:
                factors.append(ExplanationFactor(label, 0.0, "negative"))

        factors.sort(key=lambda f: f.contribution, reverse=True)
        positive_labels = [f.label for f in factors if f.kind == "positive"]
        summary = (
            "Approved because: " + "; ".join(positive_labels[:3])
            if positive_labels
            else f"Approved with score {scoring.score:.0f} (band {scoring.band})"
        )

        return {
            "top_factors": [f.label for f in factors],
            "factors": [
                {"label": f.label, "contribution": f.contribution, "kind": f.kind} for f in factors
            ],
            "flags": flags,
            "layer_scores": {
                "identity_score": identity.score,
                "alt_data_score": affordability.wallet_activity_score,
                "ml_score": round(scoring.score, 2),
            },
            "model_version": scoring.model_version,
            "summary": summary,
        }

    def build_partial_approval(
        self,
        *,
        identity: IdentityResult,
        affordability: AffordabilityResult,
        scoring: ScoreResult,
        flags: list[str],
        requested_amount: float,
        approved_amount: float,
    ) -> dict:
        base = self.build_approval(identity=identity, affordability=affordability, scoring=scoring, flags=flags)
        note = (
            f"Approved for {approved_amount:.0f} instead of the requested {requested_amount:.0f}, "
            "based on your current credit limit"
        )
        base["factors"] = [{"label": note, "contribution": 0.0, "kind": "negative"}] + base["factors"]
        base["top_factors"] = [note] + base["top_factors"]
        base["summary"] = f"Partially approved: {note}"
        return base

    def build_increase_down_payment(
        self,
        *,
        scoring: ScoreResult,
        requested_amount: float,
        limit: float,
        suggested_down_payment_pct: float,
    ) -> dict:
        reason = (
            f"Requested amount {requested_amount:.0f} exceeds your financeable limit of {limit:.0f} at the "
            f"current down payment. Increasing the down payment to {suggested_down_payment_pct:.0f}% would "
            "bring the financed amount within your limit."
        )
        return {
            "top_factors": [reason],
            "factors": [{"label": reason, "contribution": 0.0, "kind": "negative"}],
            "flags": [],
            "layer_scores": {"identity_score": 0.0, "alt_data_score": 0.0, "ml_score": round(scoring.score, 2)},
            "model_version": scoring.model_version,
            "summary": f"Increase down payment to {suggested_down_payment_pct:.0f}% to proceed",
        }

    def build_rejection(self, reason: str, flags: list[str]) -> dict:
        return {
            "top_factors": [reason],
            "factors": [{"label": reason, "contribution": 0.0, "kind": "negative"}],
            "flags": flags,
            "layer_scores": {"identity_score": 0.0, "alt_data_score": 0.0, "ml_score": 0.0},
            "model_version": "policy-v1",
            "summary": f"Rejected because: {reason}",
        }
