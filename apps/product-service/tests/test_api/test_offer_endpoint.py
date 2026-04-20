from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_offer_returns_multiple_plans(client, db_session, make_product):
    """When plan_months is not specified, all three plans are returned.

    DESIGN-06 FIX: MultipleOffersResponse no longer contains 'financing_offer'
    to avoid ambiguity about which plan is "selected". Callers must iterate
    'financing_offers' to display options.
    """
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer")
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
async def test_offer_single_plan_returns_single_offer(client, db_session, make_product):
    """When plan_months is specified, a SingleOfferResponse is returned."""
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 6})
    assert res.status_code == 200
    payload = res.json()
    assert "financing_offer" in payload
    assert payload["financing_offer"]["plan_months"] == 6
    assert "financing_offers" not in payload


@pytest.mark.asyncio
async def test_offer_rejects_out_of_stock(client, db_session, make_product):
    product = await make_product(db_session, in_stock=False, stock_status="out_of_stock")
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 3})
    assert res.status_code == 422
    assert res.json()["detail"] == "OUT_OF_STOCK"
