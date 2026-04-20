from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


class PricingService:
    _MARKUP_BY_PLAN = {
        3: Decimal("2.5"),
        6: Decimal("7.0"),
        12: Decimal("12.0"),
    }

    def calculate_offer(self, cost_price: Decimal, plan_months: int, down_payment_pct: Decimal = Decimal("30.0")) -> dict:
        if cost_price <= Decimal("0"):
            raise ValueError("INVALID_PRICE")
        if down_payment_pct < Decimal("25.0") or down_payment_pct > Decimal("40.0"):
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

    def calculate_multiple_offers(self, cost_price: Decimal, down_payment_pct: Decimal = Decimal("30.0")) -> list[dict]:
        return [
            self.calculate_offer(cost_price=cost_price, plan_months=plan_months, down_payment_pct=down_payment_pct)
            for plan_months in sorted(self._MARKUP_BY_PLAN.keys())
        ]
