from decimal import Decimal

from src.config import settings
from src.services.pricing_service import PricingService


def test_is_shariah_approved_false_without_configured_reference(monkeypatch):
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_REFERENCE", "")
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_DATE", "")
    assert PricingService().is_shariah_approved is False


def test_is_shariah_approved_true_with_configured_reference_and_date(monkeypatch):
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_REFERENCE", "SB-RES-2026-014")
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_DATE", "2026-08-01")
    assert PricingService().is_shariah_approved is True


def test_is_shariah_approved_false_with_only_reference_no_date(monkeypatch):
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_REFERENCE", "SB-RES-2026-014")
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_DATE", "")
    assert PricingService().is_shariah_approved is False


def test_calculate_offer_for_three_month_plan():
    service = PricingService()

    offer = service.calculate_offer(Decimal("10000.00"), plan_months=3, down_payment_pct=Decimal("30.0"))

    assert offer["profit_rate_pct"] == Decimal("2.5")
    assert offer["profit_amount"] == Decimal("250.00")
    assert offer["total_repayable"] == Decimal("10250.00")
    assert offer["down_payment_amount"] == Decimal("3075.00")
    assert offer["installment_count"] == 3
    assert offer["installment_amount"] == Decimal("2391.67")
    assert offer["bi_weekly_installment_count"] == 6
    assert offer["bi_weekly_amount"] == Decimal("1195.83")


def test_calculate_offer_for_twelve_month_plan():
    service = PricingService()

    offer = service.calculate_offer(Decimal("10000.00"), plan_months=12, down_payment_pct=Decimal("30.0"))

    assert offer["profit_rate_pct"] == Decimal("12.0")
    assert offer["profit_amount"] == Decimal("1200.00")
    assert offer["total_repayable"] == Decimal("11200.00")
    assert offer["down_payment_amount"] == Decimal("3360.00")
    assert offer["installment_count"] == 12


def test_calculate_offer_rejects_invalid_plan():
    service = PricingService()

    try:
        service.calculate_offer(Decimal("10000.00"), plan_months=5)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "INVALID_PLAN"

def test_calculate_offer_rejects_invalid_downpayment():
    service = PricingService()

    try:
        service.calculate_offer(Decimal("10000.00"), plan_months=3, down_payment_pct=Decimal("10.0"))
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "INVALID_DOWN_PAYMENT_PERCENTAGE"

def test_calculate_multiple_offers():
    service = PricingService()
    offers = service.calculate_multiple_offers(Decimal("10000.00"))
    assert len(offers) == 3
    assert offers[0]["plan_months"] == 3
    assert offers[1]["plan_months"] == 6
    assert offers[2]["plan_months"] == 12
