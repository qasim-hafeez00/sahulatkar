from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.credit import CreditApplication
from src.policy.rule_policy import RulePolicy


@dataclass
class LimitResult:
    limit: float
    down_payment_pct: float
    blocked: bool
    reason: str | None
    flags: list[str] = field(default_factory=list)


@dataclass
class PortfolioResult:
    blocked: bool
    reason: str | None
    flags: list[str] = field(default_factory=list)


class LimitEngine:
    """Base limit -> category/merchant risk overlay -> cold-start cap -> portfolio exposure
    check -> maximum-limit clamp. Formerly split across layer6_order_overlay.py (which had
    its own copy of PROHIBITED_CATEGORIES, independently of layer1) and layer7_portfolio.py.
    Category multipliers and prohibited categories now both come from the single RulePolicy
    passed to eligibility and limit engines alike, so the two can no longer drift apart."""

    def __init__(self, policy: RulePolicy, maximum_limit: float) -> None:
        self.policy = policy
        self.maximum_limit = maximum_limit

    def apply_category_overlay(
        self,
        base_limit: float,
        base_down_payment: float,
        category: str,
    ) -> LimitResult:
        normalized = category.strip().lower()
        if normalized in self.policy.prohibited_categories:
            return LimitResult(0.0, 0.0, True, "Prohibited category", [FlagCode.PROHIBITED_CATEGORY])

        flags: list[str] = []
        mult = self.policy.category_multipliers.get(normalized, self.policy.default_category_multiplier)
        if mult < 1.0:
            flags.append(FlagCode.HIGH_RISK_CATEGORY)

        adjusted_limit = base_limit * mult
        bump = (
            self.policy.high_risk_down_payment_bump_pct
            if mult < self.policy.high_risk_multiplier_threshold
            else 0.0
        )
        adjusted_down_payment = min(base_down_payment + bump, self.policy.max_down_payment_pct)
        return LimitResult(adjusted_limit, adjusted_down_payment, False, None, flags)

    def apply_cold_start_cap(
        self, limit: float, band: str, is_first_order: bool, data_sparse: bool = False,
    ) -> float:
        """Caps exposure for a first order OR when the score itself was computed with no
        corroborating device/IP/bank-statement evidence (data_sparse) — a scorecard band built
        entirely on KYC + wallet-mock inputs is less reliable than one backed by real signal,
        regardless of whether the caller happens to also be a first-time buyer."""
        if not is_first_order and not data_sparse:
            return limit
        cap = self.policy.cold_start_caps.get(band)
        if cap is None:
            return limit
        return min(limit, cap)

    def clamp_to_maximum(self, limit: float) -> float:
        return min(limit, self.maximum_limit)

    async def check_portfolio_concentration(
        self,
        db: AsyncSession,
        user_id: str,
        requested_amount: float,
    ) -> PortfolioResult:
        user_uuid = UUID(user_id)

        current_limit_stmt = select(func.coalesce(func.max(CreditApplication.approved_limit), Decimal("0"))).where(
            CreditApplication.user_id == user_uuid,
            CreditApplication.status == "approved",
        )
        current_limit = float((await db.execute(current_limit_stmt)).scalar_one())

        projected_exposure = current_limit + requested_amount
        if projected_exposure > self.maximum_limit:
            return PortfolioResult(True, "Requested amount breaches portfolio exposure limit", [FlagCode.PORTFOLIO_LIMIT_EXCEEDED])

        utilization_ratio = projected_exposure / self.maximum_limit if self.maximum_limit else 1.0
        flags = [FlagCode.HIGH_UTILIZATION] if utilization_ratio > 0.8 else []
        return PortfolioResult(False, None, flags)
