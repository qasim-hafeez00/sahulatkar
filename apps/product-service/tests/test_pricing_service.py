from decimal import Decimal

from src.services.pricing_service import PricingService


def test_calculate_offer_for_three_month_plan():
    service = PricingService()

    offer = service.calculate_offer(Decimal("10000.00"), plan_months=3, down_payment_pct=Decimal("30.0"))

    assert offer["profit_rate_pct"] == Decimal("2.5")
    assert offer["profit_amount"] == Decimal("250.00")
    assert offer["total_repayable"] == Decimal("10250.00")
    assert offer["down_payment_amount"] == Decimal("3075.00")
    assert offer["installment_count"] == 3
    assert offer["installment_amount"] == Decimal("2391.67")


def test_calculate_offer_rejects_invalid_plan():
    service = PricingService()

    try:
        service.calculate_offer(Decimal("10000.00"), plan_months=5)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "INVALID_PLAN"
