import pytest
from sqlalchemy import select

from src.models.payment_mandate import PaymentMandate
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def test_setup_mandate_raast_success(client, test_user):
    _, token = test_user
    resp = await client.post(
        "/api/v1/payments/mandates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "gateway": "raast",
            "payer_identifier": "PK36SCBL0000001123456702",
            "max_amount_per_txn": "2500.00",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "initiated"
    assert data["mandate_id"] > 0


async def test_setup_mandate_rejects_unsupported_gateway(client, test_user):
    _, token = test_user
    resp = await client.post(
        "/api/v1/payments/mandates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "gateway": "stripe",
            "payer_identifier": "xyz",
            "max_amount_per_txn": "1000.00",
        },
    )
    assert resp.status_code == 400


async def test_setup_mandate_requires_auth(client):
    resp = await client.post(
        "/api/v1/payments/mandates",
        json={
            "gateway": "raast",
            "payer_identifier": "PK36SCBL0000001123456702",
            "max_amount_per_txn": "2500.00",
        },
    )
    assert resp.status_code == 401


async def test_list_mandates_returns_user_items(client, test_user):
    _, token = test_user

    await client.post(
        "/api/v1/payments/mandates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "gateway": "raast",
            "payer_identifier": "PK36SCBL0000001123456702",
            "max_amount_per_txn": "2500.00",
        },
    )

    resp = await client.get(
        "/api/v1/payments/mandates/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert items[0]["gateway"] in {"raast", "jazzcash"}


async def test_revoke_mandate_success(client, test_user):
    _, token = test_user
    setup = await client.post(
        "/api/v1/payments/mandates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "gateway": "raast",
            "payer_identifier": "PK36SCBL0000001123456702",
            "max_amount_per_txn": "2500.00",
        },
    )
    mandate_id = setup.json()["mandate_id"]

    resp = await client.delete(
        f"/api/v1/payments/mandates/{mandate_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


async def test_revoke_mandate_not_found(client, test_user):
    _, token = test_user
    resp = await client.delete(
        "/api/v1/payments/mandates/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_legacy_setup_alias_works(client, test_user):
    _, token = test_user
    resp = await client.post(
        "/api/v1/payments/mandates/setup",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "gateway": "raast",
            "payer_identifier": "PK36SCBL0000001123456702",
            "max_amount_per_txn": "2500.00",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "initiated"


async def test_legacy_revoke_alias_works(client, test_user):
    _, token = test_user
    setup = await client.post(
        "/api/v1/payments/mandates",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "gateway": "raast",
            "payer_identifier": "PK36SCBL0000001123456702",
            "max_amount_per_txn": "2500.00",
        },
    )
    mandate_id = setup.json()["mandate_id"]

    async with TestingSessionLocal() as session:
        mandate = await session.get(PaymentMandate, mandate_id)
        mandate_ref = mandate.mandate_reference

    resp = await client.post(
        f"/api/v1/payments/mandates/{mandate_ref}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
