from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


class PricingService:
    _MARKUP_BY_PLAN = {
        3: Decimal("2.5"),
        4: Decimal("4.0"),
        6: Decimal("7.0"),
    }

    def calculate_offer(self, cost_price: Decimal, plan_months: int, down_payment_pct: Decimal = Decimal("30.0")) -> dict:
        if plan_months not in self._MARKUP_BY_PLAN:
            raise ValueError("INVALID_PLAN")

        q = Decimal("0.01")
        rate_pct = self._MARKUP_BY_PLAN[plan_months]
        profit_amount = (cost_price * rate_pct / Decimal("100")).quantize(q, rounding=ROUND_HALF_UP)
        total_repayable = (cost_price + profit_amount).quantize(q, rounding=ROUND_HALF_UP)
        down_payment_amount = (total_repayable * down_payment_pct / Decimal("100")).quantize(q, rounding=ROUND_HALF_UP)
        financed_amount = (total_repayable - down_payment_amount).quantize(q, rounding=ROUND_HALF_UP)
        installment_amount = (financed_amount / Decimal(str(plan_months))).quantize(q, rounding=ROUND_HALF_UP)

        return {
            "plan_months": plan_months,
            "profit_rate_pct": rate_pct,
            "cost_price": cost_price.quantize(q, rounding=ROUND_HALF_UP),
            "profit_amount": profit_amount,
            "total_repayable": total_repayable,
            "down_payment_amount": down_payment_amount,
            "installment_count": plan_months,
            "installment_amount": installment_amount,
        }
