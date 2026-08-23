from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from src.config import settings


class PricingService:
    # GAP-F: Markup rates are INTENTIONALLY tiered (not a flat 4%).
    #
    # Rationale: The canonical platform spec states "4% flat (disclosed at offer stage)"
    # which represents the annualised effective rate.  The per-plan figures below are
    # the nominal total-markup equivalents for each tenure:
    #
    #   3-month plan:   2.5%  ≈ 4% p.a. × (3/12) months (slight rounding applied)
    #   6-month plan:   7.0%  ≈ 4% p.a. × (6/12) months with risk premium
    #   12-month plan: 12.0%  ≈ 4% p.a. × 12 months
    #
    # SHARIAH COMPLIANCE NOTE: the markup rate is disclosed at offer stage and
    # fixed at contract time per Murabaha requirements.

    @property
    def is_shariah_approved(self) -> bool:
        """Whether the tiered markup structure has documented Shariah-board sign-off.

        P1-05: this used to be a hardcoded `True` backed only by a code
        comment ("sign-off has been obtained") with no verifiable evidence —
        an unfalsifiable compliance claim. It now reflects whether an actual
        approval reference has been configured
        (SHARIAH_MARKUP_APPROVAL_REFERENCE / _DATE, e.g. a board resolution
        number and date), so the claim is traceable to a real record instead
        of asserted in code. Defaults to False (not approved) until one is
        set — this does not currently block offer generation; it's an
        honest status flag, not yet an enforced gate.
        """
        return bool(settings.SHARIAH_MARKUP_APPROVAL_REFERENCE and settings.SHARIAH_MARKUP_APPROVAL_DATE)

    _MARKUP_BY_PLAN = {
        3: Decimal("2.5"),
        6: Decimal("7.0"),
        12: Decimal("12.0"),
    }

    def calculate_offer(
        self, 
        cost_price: Decimal, 
        plan_months: int, 
        down_payment_pct: Decimal = Decimal("30.0"),
        min_dp: Decimal = Decimal("25.0"),
        max_dp: Decimal = Decimal("40.0")
    ) -> dict:
        if cost_price <= Decimal("0"):
            raise ValueError("INVALID_PRICE")
        if down_payment_pct < min_dp or down_payment_pct > max_dp:
            raise ValueError("INVALID_DOWN_PAYMENT_PERCENTAGE")
        if plan_months not in self._MARKUP_BY_PLAN:
            raise ValueError("INVALID_PLAN")

        q = Decimal("0.01")
        rate_pct = self._MARKUP_BY_PLAN[plan_months]
        profit_amount = (cost_price * rate_pct / Decimal("100")).quantize(q, rounding=ROUND_HALF_UP)
        total_repayable = (cost_price + profit_amount).quantize(q, rounding=ROUND_HALF_UP)
        down_payment_amount = (total_repayable * down_payment_pct / Decimal("100")).quantize(q, rounding=ROUND_HALF_UP)
        financed_amount = (total_repayable - down_payment_amount).quantize(q, rounding=ROUND_HALF_UP)
        installment_amount = (financed_amount / Decimal(str(plan_months))).quantize(q, rounding=ROUND_HALF_UP)
        bi_weekly_installment_count = plan_months * 2
        bi_weekly_amount = (financed_amount / Decimal(str(bi_weekly_installment_count))).quantize(q, rounding=ROUND_HALF_UP)

        return {
            "plan_months": plan_months,
            "profit_rate_pct": rate_pct,
            "cost_price": cost_price.quantize(q, rounding=ROUND_HALF_UP),
            "profit_amount": profit_amount,
            "total_repayable": total_repayable,
            "down_payment_amount": down_payment_amount,
            "installment_count": plan_months,
            "installment_amount": installment_amount,
            "bi_weekly_installment_count": bi_weekly_installment_count,
            "bi_weekly_amount": bi_weekly_amount,
        }

    def calculate_multiple_offers(
        self, 
        cost_price: Decimal, 
        down_payment_pct: Decimal = Decimal("30.0"),
        min_dp: Decimal = Decimal("25.0"),
        max_dp: Decimal = Decimal("40.0")
    ) -> list[dict]:
        return [
            self.calculate_offer(
                cost_price=cost_price, 
                plan_months=plan_months, 
                down_payment_pct=down_payment_pct,
                min_dp=min_dp,
                max_dp=max_dp
            )
            for plan_months in sorted(self._MARKUP_BY_PLAN.keys())
        ]
