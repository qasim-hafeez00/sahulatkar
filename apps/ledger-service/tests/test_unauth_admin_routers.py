"""
Phase 0 security regression tests.

Audit finding: `/entries`, `/accounts`, and `/periods` shipped with zero
authentication at all, duplicating functionality already safely exposed under
`/admin/finance/*` with `require_admin_role`. These tests assert every route
in the three routers now enforces the same admin-role gate.
"""
import pytest
from datetime import date
from decimal import Decimal

from src.accounting.accounts import ACCOUNT_CODES

pytestmark = pytest.mark.asyncio

FINANCE_ANALYST = {"X-Actor-Type": "admin", "X-Actor-Roles": "finance_analyst"}
SUPER_ADMIN = {"X-Actor-Type": "admin", "X-Actor-Roles": "super_admin"}


async def test_accounts_list_requires_admin_role(client):
    response = await client.get("/accounts/")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_accounts_list_allows_finance_analyst(client, seed_ledger_accounts):
    response = await client.get("/accounts/", headers=FINANCE_ANALYST)
    assert response.status_code == 200


async def test_account_detail_requires_admin_role(client, seed_ledger_accounts):
    response = await client.get(f"/accounts/{ACCOUNT_CODES['cash']}")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_account_ledger_requires_admin_role(client, seed_ledger_accounts):
    response = await client.get(f"/accounts/{ACCOUNT_CODES['cash']}/ledger")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_periods_list_requires_admin_role(client):
    response = await client.get("/periods/")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_periods_list_allows_finance_analyst(client):
    response = await client.get("/periods/", headers=FINANCE_ANALYST)
    assert response.status_code == 200


async def test_period_close_rejects_finance_analyst(client):
    # Period close/reopen is reserved for super_admin, same bar as
    # /admin/finance/periods/{key}/close.
    response = await client.post(
        "/periods/2026-01/close",
        json={"closed_by": "ops"},
        headers=FINANCE_ANALYST,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "INSUFFICIENT_ADMIN_ROLE"


async def test_period_close_requires_admin_role(client):
    response = await client.post("/periods/2026-01/close", json={"closed_by": "ops"})
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_period_reopen_requires_admin_role(client):
    response = await client.post("/periods/2026-01/reopen")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_entries_list_requires_admin_role(client):
    response = await client.get("/entries/")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_entries_list_allows_finance_analyst(client, seed_ledger_accounts):
    response = await client.get("/entries/", headers=FINANCE_ANALYST)
    assert response.status_code == 200


async def test_entry_detail_requires_admin_role(client):
    response = await client.get("/entries/JE-DOES-NOT-EXIST")
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_manual_entry_requires_admin_role(client):
    response = await client.post(
        "/entries/manual",
        json={
            "description": "Test manual entry",
            "lines": [
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 100.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["owner_equity"], "debit_amount": 0.0, "credit_amount": 100.0},
            ],
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"


async def test_manual_entry_rejects_finance_analyst(client, seed_ledger_accounts):
    # Manual postings mutate the GL directly and are gated at super_admin only,
    # unlike the read endpoints which finance_analyst can use.
    response = await client.post(
        "/entries/manual",
        json={
            "description": "Test manual entry",
            "lines": [
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 100.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["owner_equity"], "debit_amount": 0.0, "credit_amount": 100.0},
            ],
        },
        headers=FINANCE_ANALYST,
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "INSUFFICIENT_ADMIN_ROLE"


async def test_manual_entry_and_reversal_allowed_for_super_admin(client, seed_ledger_accounts):
    create_response = await client.post(
        "/entries/manual",
        json={
            "description": "Test manual entry",
            "lines": [
                {"account_code": ACCOUNT_CODES["cash"], "debit_amount": 100.0, "credit_amount": 0.0},
                {"account_code": ACCOUNT_CODES["owner_equity"], "debit_amount": 0.0, "credit_amount": 100.0},
            ],
        },
        headers=SUPER_ADMIN,
    )
    assert create_response.status_code == 200
    entry_number = create_response.json()["entry_number"]

    reverse_response = await client.post(
        f"/entries/{entry_number}/reverse",
        json={"reason": "test reversal"},
        headers=SUPER_ADMIN,
    )
    assert reverse_response.status_code == 200


async def test_entries_reverse_requires_admin_role(client):
    response = await client.post("/entries/JE-DOES-NOT-EXIST/reverse", json={"reason": "test"})
    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_ROLE_REQUIRED"
