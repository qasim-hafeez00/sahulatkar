import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sk_shared.models.order import Order
from sk_shared.constants import OrderState
from src.config import settings

pytestmark = pytest.mark.asyncio

async def test_product_extracted_callback_success(client: AsyncClient, db_session, test_user):
    user, _ = test_user
    from sk_shared.models.product import Merchant, Product

    merchant = Merchant(name="Demo Merchant", normalized_name="demo-merchant", domain="example.com")
    db_session.add(merchant)
    await db_session.flush()
    product = Product(
        merchant_id=merchant.id,
        name="IPhone 15",
        url="https://example.com/item",
        currency="PKR",
        cost_price=90000.0,
        sale_price=100000.0,
        in_stock=True,
    )
    db_session.add(product)
    await db_session.commit()

    # 1. Create a dummy order in 'url_received' state
    order = Order(
        user_id=user.id,
        status="url_received",
        total_amount=0,
        product_description="https://example.com/item"
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    # 2. Call internal callback
    headers = {"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN}
    payload = {
        "product_id": product.id,
        "name": "IPhone 15",
        "cost_price": 90000.0,
        "sale_price": 100000.0,
        "currency": "PKR",
        "down_payment_pct": 25.0,
        "in_stock": True
    }
    
    response = await client.post(
        f"/api/v1/internal/orders/{order.id}/product-extracted",
        json=payload,
        headers=headers
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # 3. Verify DB state
    await db_session.refresh(order)
    assert order.status == OrderState.OFFER_PRESENTED
    assert float(order.total_amount) == 100000.0
    assert float(order.down_payment_amount) == 25000.0
    assert order.product_id == product.id

async def test_product_extracted_invalid_token(client: AsyncClient, test_user):
    headers = {"X-Internal-Token": "wrong-token"}
    response = await client.post(
        "/api/v1/internal/orders/1/product-extracted",
        json={"product_id": 1, "name": "x", "cost_price": 1, "sale_price": 1},
        headers=headers
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "INVALID_INTERNAL_TOKEN"

async def test_extraction_failed_callback(client: AsyncClient, db_session, test_user):
    user, _ = test_user
    order = Order(
        user_id=user.id,
        status="url_received",
        total_amount=0,
        product_description="https://example.com/bad-item"
    )
    db_session.add(order)
    await db_session.commit()
    
    headers = {"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN}
    response = await client.post(
        f"/api/v1/internal/orders/{order.id}/extraction-failed",
        json={"reason": "Scraping blocked"},
        headers=headers
    )
    assert response.status_code == 200
    
    await db_session.refresh(order)
    assert order.status == "extraction_failed"

async def test_payment_confirmed_callback(client: AsyncClient, db_session, test_user, redis_mock):
    user, _ = test_user
    # 1. Create order and transaction
    order = Order(user_id=user.id, status="offer_accepted", total_amount=1000)
    db_session.add(order)
    await db_session.flush()
    
    from sk_shared.models.payment import PaymentTransaction
    txn = PaymentTransaction(
        user_id=user.id,
        order_id=order.id,
        amount=250,
        status="pending",
        gateway="manual"
    )
    db_session.add(txn)
    await db_session.commit()
    
    # 2. Confirm
    headers = {"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN}
    response = await client.post(
        f"/api/v1/internal/payments/{txn.id}/confirm",
        json={"gateway_txn_id": "GYZ-789", "status": "confirmed"},
        headers=headers
    )
    assert response.status_code == 200
    
    await db_session.refresh(txn)
    assert txn.status == "confirmed"
    assert txn.gateway_txn_id == "GYZ-789"
