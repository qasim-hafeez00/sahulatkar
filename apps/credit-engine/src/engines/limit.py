from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.auth import User
from sk_shared.models.credit import CreditApplication
from sk_shared.models.payment import Installment, Loan
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

    async def has_repayment_track_record(self, db: AsyncSession, user_id: str) -> bool:
        """Graduates a proven customer out of the cold-start cap using real, already-available
        repayment history (Loan/Installment, owned by payment-orchestrator but written to the
        same physical database credit-engine reads elsewhere too — see
        AffordabilityEngine._latest_bank_statement / pipeline._get_user_int_id for the same
        uuid->users.id resolution pattern), independent of the device/IP/bank-statement signal
        `data_sparse` depends on. That signal is permanently unavailable in production (no
        wallet/device-fingerprinting/IP-intelligence vendor is integrated — see wallet.py /
        identity.py / fraud.py), so without this, its "graduate out of cold-start" exit could
        never fire for a real applicant, and every repeat customer would be capped forever.

        Rule: at least `policy.graduation_min_repaid_loans` fully-repaid (`Loan.status ==
        "fully_paid"`) prior loans, with ZERO evidence anywhere in the user's loan history of a
        missed or late installment. See RulePolicy.graduation_min_repaid_loans for why that
        count defaults to 3.

        Deliberately conservative in both directions — this is underwriting logic for a
        regulated lender, so it must only ever relax the cap for a genuinely proven customer:
          - Only `fully_paid` loans count toward the threshold. `active`/`partially_paid` loans
            aren't finished yet; `defaulted`/`written_off`/`disputed` are exactly the outcomes
            the cold-start cap exists to protect against.
          - ANY negative signal disqualifies the user entirely, not just the loan it occurred
            on: a nonzero `Loan.late_fee_total` on ANY of the user's loans (fully paid or not),
            or any `Installment` ever left in `overdue`/`defaulted` status, or carrying a
            nonzero `late_fee_amount` (checked independently of `late_fee_total` in case a
            future write path updates one without the other) — any of these means this returns
            False regardless of how many clean loans exist elsewhere in the history.
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError:
            return False
        user_int_id = (await db.execute(select(User.id).where(User.uuid == user_uuid))).scalar_one_or_none()
        if user_int_id is None:
            return False

        any_late_fee_stmt = select(func.count()).select_from(Loan).where(
            Loan.user_id == user_int_id,
            Loan.deleted_at.is_(None),
            Loan.late_fee_total > 0,
        )
        if (await db.execute(any_late_fee_stmt)).scalar_one() > 0:
            return False

        any_bad_installment_stmt = select(func.count()).select_from(Installment).where(
            Installment.user_id == user_int_id,
            Installment.deleted_at.is_(None),
            or_(
                Installment.status.in_(("overdue", "defaulted")),
                Installment.late_fee_amount > 0,
            ),
        )
        if (await db.execute(any_bad_installment_stmt)).scalar_one() > 0:
            return False

        fully_paid_count_stmt = select(func.count()).select_from(Loan).where(
            Loan.user_id == user_int_id,
            Loan.deleted_at.is_(None),
            Loan.status == "fully_paid",
        )
        fully_paid_count = (await db.execute(fully_paid_count_stmt)).scalar_one()
        return fully_paid_count >= self.policy.graduation_min_repaid_loans

    def clamp_to_maximum(self, limit: float) -> float:
        return min(limit, self.maximum_limit)

    async def check_portfolio_concentration(
        self,
        db: AsyncSession,
        user_id: str,
        requested_amount: float,
    ) -> PortfolioResult:
        user_uuid = UUID(user_id)

        # CE-HIGH-01: DB-level layer of the TOCTOU guard, alongside (not instead of) the
        # per-user Redis lock routes.py's /credit/apply now holds across this check and the
        # CreditApplication insert that follows it (see _portfolio_lock_key there). Locking
        # the user's own row means any concurrent transaction that reaches this same check
        # for this user — including a future caller that doesn't go through that route — is
        # serialized behind whichever one commits its CreditApplication first, on Postgres.
        # A no-op on SQLite (as with the identical with_for_update() use in
        # payment-orchestrator's payments.py), so it does nothing in this test suite; the
        # Redis lock is what actually closes the race there.
        await db.execute(select(User.id).where(User.uuid == user_uuid).with_for_update())

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
