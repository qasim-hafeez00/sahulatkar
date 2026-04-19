import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_compliance_audit_trail_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/compliance/audit-trail", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


async def test_admin_global_audit_trail_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/audit-trail", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


async def test_shariah_audit_summary_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/compliance/shariah-audit", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "allocations_count" in data
    assert "total_late_fee_allocated" in data


async def test_charity_report_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/compliance/charity-report", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


async def test_financial_summary_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/compliance/financial-summary", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "total_payments" in data
    assert "transactions_count" in data


async def test_reconciliation_endpoint(client: AsyncClient, test_admin):
    _, admin_token = test_admin
    response = await client.get("/api/v1/admin/compliance/reconciliation", headers=_auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "total_transactions" in data
    assert "reconciled_transactions" in data
