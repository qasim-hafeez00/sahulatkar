import httpx
import pytest
import os

# Base URLs for services (defaults to staging URLs from master plan)
GATEWAY_URL = os.getenv("GATEWAY_URL", "https://staging-api.sahulatkar.com")
PRODUCT_URL = os.getenv("PRODUCT_URL", "https://staging-product.sahulatkar.com")
CREDIT_URL = os.getenv("CREDIT_URL", "https://staging-credit.sahulatkar.com")
PAYMENT_URL = os.getenv("PAYMENT_URL", "https://staging-payment.sahulatkar.com")
LEDGER_URL = os.getenv("LEDGER_URL", "https://staging-ledger.sahulatkar.com")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "https://staging-notification.sahulatkar.com")
WEB_CUSTOMER_URL = os.getenv("WEB_CUSTOMER_URL", "https://staging.sahulatkar.com")
WEB_ADMIN_URL = os.getenv("WEB_ADMIN_URL", "https://staging-admin.sahulatkar.com")

@pytest.mark.asyncio
async def test_gateway_health():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{GATEWAY_URL}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_product_service_health():
    async with httpx.AsyncClient() as client:
        # Product service is behind gateway, but we might test internal endpoint in staging
        response = await client.get(f"{PRODUCT_URL}/health")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_credit_engine_health():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{CREDIT_URL}/health")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_payment_orchestrator_health():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PAYMENT_URL}/health")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_ledger_service_health():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{LEDGER_URL}/health")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_notification_service_health():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{NOTIFICATION_URL}/health")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_web_customer_home():
    async with httpx.AsyncClient() as client:
        response = await client.get(WEB_CUSTOMER_URL)
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_web_admin_login_page():
    async with httpx.AsyncClient() as client:
        response = await client.get(WEB_ADMIN_URL)
        assert response.status_code == 200
