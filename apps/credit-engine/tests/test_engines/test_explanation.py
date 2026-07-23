from src.engines.affordability import AffordabilityResult
from src.engines.explanation import ExplanationBuilder
from src.engines.identity import IdentityResult
from src.engines.scoring import ScoreResult


def _scoring(identity_contribution: float, alt_data_contribution: float) -> ScoreResult:
    return ScoreResult(
        score=identity_contribution + alt_data_contribution,
        band="A",
        base_limit=25000.0,
        down_payment_pct=25.0,
        model_version="scorecard-v1",
        identity_contribution=identity_contribution,
        alt_data_contribution=alt_data_contribution,
    )


def test_approval_factors_are_ranked_by_contribution_descending():
    builder = ExplanationBuilder()
    explanation = builder.build_approval(
        identity=IdentityResult(score=90.0, flags=["identity_strong"]),
        affordability=AffordabilityResult(wallet_activity_score=20.0, income_signal="stable", provider="mock-jazzcash"),
        scoring=_scoring(identity_contribution=720.0, alt_data_contribution=16.0),
        flags=["identity_strong"],
    )
    contributions = [f["contribution"] for f in explanation["factors"]]
    assert contributions == sorted(contributions, reverse=True)
    assert explanation["factors"][0]["kind"] == "positive"
    assert "Approved because:" in explanation["summary"]


def test_approval_explanation_surfaces_negative_flags_as_factors():
    builder = ExplanationBuilder()
    explanation = builder.build_approval(
        identity=IdentityResult(score=90.0, flags=[]),
        affordability=AffordabilityResult(wallet_activity_score=55.0, income_signal="stable", provider="mock-jazzcash"),
        scoring=_scoring(identity_contribution=720.0, alt_data_contribution=44.0),
        flags=["high_risk_category", "high_utilization"],
    )
    negative_labels = [f["label"] for f in explanation["factors"] if f["kind"] == "negative"]
    assert any("elevated risk" in label for label in negative_labels)
    assert any("portfolio exposure" in label for label in negative_labels)


def test_approval_explanation_preserves_layer_scores_shape_for_api_compat():
    builder = ExplanationBuilder()
    explanation = builder.build_approval(
        identity=IdentityResult(score=90.0, flags=[]),
        affordability=AffordabilityResult(wallet_activity_score=55.0, income_signal="stable", provider="mock-jazzcash"),
        scoring=_scoring(identity_contribution=720.0, alt_data_contribution=44.0),
        flags=[],
    )
    assert explanation["layer_scores"] == {
        "identity_score": 90.0,
        "alt_data_score": 55.0,
        "ml_score": 764.0,
    }
    assert explanation["model_version"] == "scorecard-v1"


def test_rejection_explanation_shape():
    builder = ExplanationBuilder()
    explanation = builder.build_rejection("KYC must be approved before credit assessment", ["kyc_not_approved"])
    assert explanation["top_factors"] == ["KYC must be approved before credit assessment"]
    assert explanation["flags"] == ["kyc_not_approved"]
    assert explanation["summary"].startswith("Rejected because:")
