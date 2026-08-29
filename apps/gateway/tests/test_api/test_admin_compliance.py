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


async def test_admin_can_record_and_list_shariah_board_approval(client: AsyncClient, test_admin):
    """HIGH regression: an admin must be able to record a real Shariah board
    approval for a contract template_version -- the backing record that
    ContractGeneratorService.generate_murabaha checks before setting
    validated_by_shariah_board True."""
    _, admin_token = test_admin

    create_resp = await client.post(
        "/api/v1/admin/compliance/shariah-board-approvals",
        headers=_auth(admin_token),
        json={
            "template_version": "1.0",
            "approved_by": "Shariah Board Chair",
            "notes": "Approved after Q3 2026 review",
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["template_version"] == "1.0"
    assert body["approved_by"] == "Shariah Board Chair"

    list_resp = await client.get("/api/v1/admin/compliance/shariah-board-approvals", headers=_auth(admin_token))
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(item["template_version"] == "1.0" for item in items)
