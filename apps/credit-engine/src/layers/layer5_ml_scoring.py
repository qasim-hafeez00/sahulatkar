from dataclasses import dataclass
from typing import Any


@dataclass
class MLScoreResult:
    score: float
    band: str
    base_limit: float
    down_payment_pct: float
    model_version: str


class XGBoostScorer:
    def __init__(self, model_version: str = "xgb-mock-v1") -> None:
        self.model_version = model_version

    def score(self, features: dict[str, Any]) -> MLScoreResult:
        identity_score = float(features.get("identity_score", 0.0))
        alt_data_score = float(features.get("alt_data_score", 50.0))

        score = min(max((identity_score * 8.0) + (alt_data_score * 0.8), 0.0), 900.0)

        if score >= 800:
            return MLScoreResult(score=score, band="A", base_limit=25000.0, down_payment_pct=25.0, model_version=self.model_version)
        if score >= 700:
            return MLScoreResult(score=score, band="B", base_limit=15000.0, down_payment_pct=25.0, model_version=self.model_version)
        if score >= 600:
            return MLScoreResult(score=score, band="C", base_limit=8000.0, down_payment_pct=30.0, model_version=self.model_version)
        if score >= 500:
            return MLScoreResult(score=score, band="D", base_limit=5000.0, down_payment_pct=35.0, model_version=self.model_version)
        return MLScoreResult(score=score, band="F", base_limit=0.0, down_payment_pct=0.0, model_version=self.model_version)
