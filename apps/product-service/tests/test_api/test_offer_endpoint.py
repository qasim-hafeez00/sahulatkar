from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_offer_returns_multiple_plans(client, db_session, make_product):
    product = await make_product(db_session, cost_price=Decimal("10000.00"), sale_price=Decimal("10000.00"))
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer")
    assert res.status_code == 200
    payload = res.json()
    assert len(payload["financing_offers"]) == 3
    assert payload["financing_offer"]["plan_months"] in {3, 6, 12}


@pytest.mark.asyncio
async def test_offer_rejects_out_of_stock(client, db_session, make_product):
    product = await make_product(db_session, in_stock=False, stock_status="out_of_stock")
    await db_session.commit()

    res = await client.get(f"/api/v1/products/{product.uuid}/offer", params={"plan_months": 3})
    assert res.status_code == 422
    assert res.json()["detail"] == "OUT_OF_STOCK"
