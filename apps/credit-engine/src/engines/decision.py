from __future__ import annotations

import time
from typing import Any

from sk_shared.credit_reason_codes import FlagCode
from src.engines.affordability import AffordabilityResult
from src.engines.explanation import ExplanationBuilder
from src.engines.identity import IdentityResult
from src.engines.scoring import ScoreResult


class DecisionEngine:
    """Assembles the sub-engine outputs into the final decision dict via ExplanationBuilder.

    Five outcomes: approved, rejected, partial_approval (order approved at a reduced amount
    when the limit covers most but not all of it), increase_down_payment (a larger upfront
    payment would bring the financed portion within the limit), and manual_review — which
    isn't a distinct outcome here but a `manual_review_required` flag riding along any of the
    above, since FraudEngine's borderline cases (Phase 2) don't block the decision, they just
    route it for human follow-up after the fact.

    `reduce_limit` from the plan's outcome list is deliberately not a branch here — reducing
    an existing account's standing limit is an account-level, admin-triggered action (already
    served by /admin/credit/override), not a per-order decision outcome.
    """

    def __init__(self, explanation_builder: ExplanationBuilder | None = None) -> None:
        self.explanation_builder = explanation_builder or ExplanationBuilder()

    def build_approval(
        self,
        *,
        identity: IdentityResult,
        affordability: AffordabilityResult,
        scoring: ScoreResult,
        limit: float,
        down_payment_pct: float,
        flags: list[str],
        start_time: float,
    ) -> dict[str, Any]:
        explanation = self.explanation_builder.build_approval(
            identity=identity, affordability=affordability, scoring=scoring, flags=flags,
        )
        return {
            "approved": True,
            "outcome": "approved",
            "risk_band": scoring.band,
            "approved_limit": float(limit),
            "down_payment_pct": float(down_payment_pct),
            "rejection_reason": None,
            "manual_review_required": FlagCode.MANUAL_REVIEW_REQUIRED in flags,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "explanation": explanation,
        }

    def build_partial_approval(
        self,
        *,
        identity: IdentityResult,
        affordability: AffordabilityResult,
        scoring: ScoreResult,
        limit: float,
        down_payment_pct: float,
        requested_amount: float,
        flags: list[str],
        start_time: float,
    ) -> dict[str, Any]:
        explanation = self.explanation_builder.build_partial_approval(
            identity=identity, affordability=affordability, scoring=scoring, flags=flags,
            requested_amount=requested_amount, approved_amount=limit,
        )
        return {
            "approved": True,
            "outcome": "partial_approval",
            "risk_band": scoring.band,
            "approved_limit": float(limit),
            "requested_amount": float(requested_amount),
            "down_payment_pct": float(down_payment_pct),
            "rejection_reason": None,
            "manual_review_required": FlagCode.MANUAL_REVIEW_REQUIRED in flags,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "explanation": explanation,
        }

    def build_increase_down_payment(
        self,
        *,
        scoring: ScoreResult,
        limit: float,
        requested_amount: float,
        suggested_down_payment_pct: float,
        flags: list[str],
        start_time: float,
    ) -> dict[str, Any]:
        explanation = self.explanation_builder.build_increase_down_payment(
            scoring=scoring, requested_amount=requested_amount, limit=limit,
            suggested_down_payment_pct=suggested_down_payment_pct,
        )
        return {
            "approved": False,
            "outcome": "increase_down_payment",
            "risk_band": scoring.band,
            "approved_limit": float(limit),
            "requested_amount": float(requested_amount),
            "down_payment_pct": round(suggested_down_payment_pct, 2),
            "suggested_down_payment_pct": round(suggested_down_payment_pct, 2),
            "rejection_reason": "Requested amount exceeds the financeable limit at the current down payment",
            "manual_review_required": FlagCode.MANUAL_REVIEW_REQUIRED in flags,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "explanation": explanation,
        }

    def build_rejection(self, reason: str, flags: list[str], start_time: float) -> dict[str, Any]:
        explanation = self.explanation_builder.build_rejection(reason, flags)
        return {
            "approved": False,
            "outcome": "rejected",
            "risk_band": "F",
            "approved_limit": 0.0,
            "down_payment_pct": 0.0,
            "rejection_reason": reason,
            "manual_review_required": False,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "explanation": explanation,
        }
