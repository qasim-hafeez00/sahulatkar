from decimal import Decimal

import pytest

from src.config import settings


@pytest.fixture(autouse=True)
def _shariah_approved(monkeypatch):
    """Most tests in this file exercise pricing/auth behavior, not the
    Shariah-approval gate itself — default to "approved" here so those tests
    aren't coupled to that gate, and have the two gate-specific tests below
    explicitly monkeypatch it back to unapproved."""
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_REFERENCE", "SB-RES-2026-014")
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_DATE", "2026-08-01")


@pytest.mark.asyncio
async def test_offer_returns_multiple_plans(client, db_session, make_product, service_header):
    """When plan_months is not specified, all three plans are returned.

    DESIGN-06 FIX: MultipleOffersResponse no longer contains 'financing_offer'
    to avoid ambiguity about which plan is "selected". Callers must iterate
    'financing_offers' to display options.
    """
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", headers=service_header)
    assert res.status_code == 200
    payload = res.json()
    assert len(payload["financing_offers"]) == 3
    # financing_offer must NOT be present on the all-plans response (DESIGN-06)
    assert "financing_offer" not in payload, (
        "MultipleOffersResponse must not expose 'financing_offer' to avoid "
        "callers assuming the first plan is the selected plan."
    )
    # Each offer contains the expected plan months
    months = {o["plan_months"] for o in payload["financing_offers"]}
    assert months == {3, 6, 12}


@pytest.mark.asyncio
async def test_offer_single_plan_returns_single_offer(client, db_session, make_product, service_header):
    """When plan_months is specified, a SingleOfferResponse is returned."""
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 6}, headers=service_header)
    assert res.status_code == 200
    payload = res.json()
    assert "financing_offer" in payload
    assert payload["financing_offer"]["plan_months"] == 6
    assert "financing_offers" not in payload


@pytest.mark.asyncio
async def test_offer_rejects_out_of_stock(client, db_session, make_product, service_header):
    product = await make_product(db_session, in_stock=False, stock_status="out_of_stock")
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 3}, headers=service_header)
    assert res.status_code == 422
    assert res.json()["detail"] == "OUT_OF_STOCK"


@pytest.mark.asyncio
async def test_offer_requires_auth(client, db_session, make_product):
    """HIGH-04 regression: GET /products/{upo_id}/offer previously had no
    auth dependency at all, inconsistent with every sibling endpoint in
    products.py. A direct, unauthenticated call must now be rejected instead
    of leaking pricing/offer data to anyone who can reach the service."""
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_offer_blocked_without_shariah_approval(client, db_session, make_product, service_header, monkeypatch):
    """HIGH-01 regression: PricingService.is_shariah_approved defaults to
    False (no configured Shariah-board approval reference/date) and must now
    actually block offer generation, not just be an honest-but-unenforced
    display flag."""
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_REFERENCE", "")
    monkeypatch.setattr(settings, "SHARIAH_MARKUP_APPROVAL_DATE", "")

    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 3}, headers=service_header)
    assert res.status_code == 503
    assert res.json()["detail"].startswith("SHARIAH_APPROVAL_REQUIRED")


@pytest.mark.asyncio
async def test_offer_allowed_with_shariah_approval_configured(client, db_session, make_product, service_header):
    """Sanity check for the other side of the gate: once a real approval
    reference + date are configured, the offer endpoint works normally."""
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 3}, headers=service_header)
    assert res.status_code == 200
