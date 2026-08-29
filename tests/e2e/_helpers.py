"""
Shared helpers for the E2E suite's non-happy-path test files
(test_kyc_and_order_failure_paths.py, test_admin_workflows.py,
test_billing_late_fee_charity.py). Deliberately NOT imported by
test_order_lifecycle.py -- that file is the original, independently-passing
happy-path suite and is left untouched so this refactor can never regress it.

Everything here talks to the same live docker-compose stack the `docker_stack`/
`base_urls` fixtures in conftest.py bring up -- no mocking.
"""
from __future__ import annotations

import random
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import asyncpg

REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE_COMPOSE = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"
_COMPOSE_PROJECT = "docker"  # matches tests/e2e/conftest.py's PROJECT pin

# Matches docker-compose.yml's postgres service and tests/e2e/conftest.py.
PG_DSN = dict(host="localhost", port=5434, user="sk_admin", password="localdev123", database="sahulatkar")

MOCK_MERCHANT_BASE = "http://e2e-mock-merchant:8080/product"
WIDGET_URL = f"{MOCK_MERCHANT_BASE}/widget-1"
WIDGET_PRICE_DRIFT_URL = f"{MOCK_MERCHANT_BASE}/widget-price-drift"
EXPECTED_PRICE = 12000.00


def unique_phone() -> str:
    digits = "".join(random.choices("0123456789", k=10))
    return f"+92{digits}"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@e2e.sahulatkar.test"


async def sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


async def poll_until(fn, predicate, *, timeout: float, interval: float = 2.0, desc: str = "condition"):
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = await fn()
        if predicate(last):
            return last
        await sleep(interval)
    raise AssertionError(f"Timed out after {timeout}s waiting for: {desc}. Last observed value: {last!r}")


async def db_fetchrow(query: str, *args) -> dict | None:
    conn = await asyncpg.connect(**PG_DSN)
    try:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def db_fetch(query: str, *args) -> list[dict]:
    conn = await asyncpg.connect(**PG_DSN)
    try:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def db_execute(query: str, *args) -> str:
    conn = await asyncpg.connect(**PG_DSN)
    try:
        return await conn.execute(query, *args)
    finally:
        await conn.close()


async def register_and_activate_customer(gw, *, phone: str | None = None, cnic: str = "12345-1234567-1") -> dict:
    """Registers a customer, verifies OTP, and runs the KYC flow to
    completion with documents that pass every dev-mode mock (NADRA CNIC
    not ending in -9, OCR/liveness URLs with no 'invalid'/'spoof'
    substring). Returns {"user_id", "access_token", "phone"} with
    gw.headers["Authorization"] already set on the passed-in client.
    """
    phone = phone or unique_phone()
    resp = await gw.post("/api/v1/auth/register/initiate", json={
        "phone": phone, "first_name": "E2E", "last_name": "Tester",
    })
    assert resp.status_code == 200, resp.text
    initiate_body = resp.json()
    otp_token = initiate_body["otp_token"]

    resp = await gw.post("/api/v1/auth/verify-otp", json={
        "otp_token": otp_token, "otp_code": initiate_body["dev_otp"],
    })
    assert resp.status_code == 200, resp.text
    auth = resp.json()
    access_token = auth["access_token"]
    user_id = auth["user_id"]

    gw.headers["Authorization"] = f"Bearer {access_token}"

    resp = await gw.post("/api/v1/kyc/start")
    assert resp.status_code == 200, resp.text

    resp = await gw.put("/api/v1/kyc/profile", json={
        "first_name": "E2E", "last_name": "Tester",
        "cnic": cnic,
        "dob": "1990-01-01T00:00:00",
        "address": "123 Test Street, Karachi",
    })
    assert resp.status_code == 200, resp.text

    for doc_type, filename, content_type in [
        ("cnic_front", "cnic_front.jpg", "image/jpeg"),
        ("cnic_back", "cnic_back.jpg", "image/jpeg"),
        ("liveness_video", "liveness.mp4", "video/mp4"),
    ]:
        resp = await gw.post(
            f"/api/v1/kyc/upload/{doc_type}",
            files={"file": (filename, b"fake-bytes-for-e2e-test", content_type)},
        )
        assert resp.status_code == 200, resp.text

    resp = await gw.post("/api/v1/kyc/submit")
    assert resp.status_code == 200, resp.text

    return {"user_id": user_id, "access_token": access_token, "phone": phone}


async def initiate_and_accept_order(gw, product_url: str, *, installment_count: int = 4) -> dict:
    """Initiates an order against a mock-merchant product URL, polls the
    offer to ready, and accepts it. Returns the accept response body plus
    the order_id."""
    resp = await gw.post("/api/v1/orders/initiate", json={"product_url": product_url})
    assert resp.status_code == 200, resp.text
    order_id = resp.json()["order_id"]

    async def _get_offer():
        r = await gw.get(f"/api/v1/orders/{order_id}/offer")
        assert r.status_code == 200, r.text
        return r.json()

    offer = await poll_until(
        _get_offer,
        lambda o: o["status"] in {"ready", "extraction_failed", "declined"},
        timeout=180.0,
        desc=f"order {order_id} offer to leave 'pending'",
    )
    assert offer["status"] == "ready", f"Extraction did not succeed: {offer}"

    resp = await gw.post(f"/api/v1/orders/{order_id}/accept", json={"installment_count": installment_count})
    assert resp.status_code == 200, resp.text
    accepted = resp.json()
    accepted["order_id"] = order_id
    return accepted


async def sign_contracts(gw, order_id: int, *, installment_count: int = 4) -> dict:
    """Generates + signs Wakalah then Murabaha for an already-accepted
    order. Returns the murabaha-sign response body."""
    resp = await gw.post("/api/v1/contracts/wakalah/generate", json={"order_id": order_id})
    assert resp.status_code == 200, resp.text
    wakalah = resp.json()

    resp = await gw.post("/api/v1/contracts/wakalah/sign", json={
        "contract_id": wakalah["contract_id"],
        "otp_code": wakalah["dev_otp"],
        "device_id": "e2e-test-device",
    })
    assert resp.status_code == 200, resp.text

    resp = await gw.post("/api/v1/contracts/murabaha/generate", json={
        "order_id": order_id, "installment_count": installment_count,
    })
    assert resp.status_code == 200, resp.text
    murabaha = resp.json()

    resp = await gw.post("/api/v1/contracts/murabaha/sign", json={
        "contract_id": murabaha["contract_id"],
        "otp_code": murabaha["dev_otp"],
        "confirmation_checkbox": True,
        "device_id": "e2e-test-device",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


async def pay_down_payment(pay, order_id: int, access_token: str, amount) -> dict:
    idem_key = f"e2e-{uuid.uuid4().hex}"
    resp = await pay.post(
        "/api/v1/payments/down-payment",
        json={
            "order_id": order_id,
            "method": "jazzcash",
            "amount_pkr": str(amount),
            "idempotency_key": idem_key,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def full_order_to_down_payment(gw, pay, product_url: str = WIDGET_URL, *, installment_count: int = 4) -> dict:
    """End-to-end helper: register+KYC -> initiate/accept order -> sign both
    contracts -> pay down payment. Returns everything a caller might need:
    user_id, access_token, order_id, down_payment_amount, down payment
    response."""
    identity = await register_and_activate_customer(gw)
    accepted = await initiate_and_accept_order(gw, product_url, installment_count=installment_count)
    order_id = accepted["order_id"]
    await sign_contracts(gw, order_id, installment_count=installment_count)
    down_payment_amount = accepted["down_payment_amount"]
    dp = await pay_down_payment(pay, order_id, identity["access_token"], down_payment_amount)
    return {
        **identity,
        "order_id": order_id,
        "down_payment_amount": down_payment_amount,
        "down_payment_response": dp,
        "accepted": accepted,
    }


async def get_virtual_card(order_id: int) -> dict | None:
    return await db_fetchrow(
        "SELECT id, issuer_card_id, status, is_used, masked_number "
        "FROM virtual_cards WHERE order_id = $1",
        order_id,
    )


async def get_purchase_execution(order_id: int) -> dict | None:
    return await db_fetchrow(
        "SELECT uuid, status, step_reached, merchant_order_id, failure_type, error_detail "
        "FROM purchase_executions WHERE order_id = $1 ORDER BY id DESC LIMIT 1",
        order_id,
    )


def run_ledger_worker(module: str, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Runs a ledger-service worker CLI entrypoint as a one-off container
    against the SAME live stack the other fixtures/tests use (`docker
    compose run --rm ledger-service python -m <module> ...`), mirroring the
    exact pattern tests/e2e/conftest.py already uses for one-off Alembic
    migration runs. extra_env lets a test override a setting (e.g.
    CHARITY_DISBURSEMENT_MIN_AGE_DAYS / SHARIAH_NISAB_PKR) for just this one
    invocation, without touching the long-running ledger-service container's
    real config.
    """
    argv = ["docker", "compose", "-p", _COMPOSE_PROJECT, "-f", str(_BASE_COMPOSE), "run", "--rm"]
    for key, value in (extra_env or {}).items():
        argv += ["-e", f"{key}={value}"]
    argv += ["ledger-service", "python", "-m", module, *args]
    # Live-verified this occasionally exceeds 120s under the full E2E stack's
    # own load (13 containers already up, other tests' Playwright checkouts
    # running) even though the worker itself completes in a few seconds when
    # the stack is idle -- the slack here is for `docker compose run`'s own
    # container-create/attach overhead under contention, not the worker.
    return subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=240)


LEDGER_HEADERS_FINANCE = {
    "X-Actor-Type": "admin",
    "X-Actor-Id": "e2e-test",
    "X-Actor-Roles": "super_admin,finance_analyst",
}


async def bootstrap_super_admin(gw, *, email: str | None = None, password: str = "E2eAdminPass!2026") -> dict:
    """Creates a real AdminUser row directly in Postgres (mirroring how
    test_order_lifecycle.py already uses direct DB access for
    test-orchestration needs the API surface has no route for -- there is no
    'create the first admin' bootstrap endpoint anywhere in Gateway), then
    drives the REAL HTTP MFA-setup dance so the returned access token is
    exactly what admin_login() issues in production: login -> 403
    MFA_SETUP_REQUIRED (X-Temp-Token) -> POST /mfa/setup -> compute a live
    TOTP code with pyotp from the returned secret -> POST /mfa/verify ->
    real login with the TOTP code.

    Requires a `roles` row named 'super_admin' to exist -- migration 067
    ("Seed the 8 canonical admin roles") only seeded 6 of RBACService's 12
    static role names and 'super_admin' was not one of them (a real,
    independently-noteworthy drift between the roles table and
    RBACService's hardcoded permission map), so this creates that row
    on-demand rather than assuming it's there.
    """
    import pyotp
    from sk_shared.security import get_password_hash

    email = email or f"e2e-admin-{uuid.uuid4().hex[:10]}@sahulatkar.test"
    password_hash = get_password_hash(password)

    conn = await asyncpg.connect(**PG_DSN)
    try:
        role_row = await conn.fetchrow(
            "INSERT INTO roles (name, description, created_at, updated_at) "
            "VALUES ('super_admin', 'E2E-seeded super_admin role', now(), now()) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
            "RETURNING id"
        )
        role_id = role_row["id"]

        admin_row = await conn.fetchrow(
            "INSERT INTO admin_users (uuid, email, password_hash, mfa_enabled, force_password_change, role_id, created_at, updated_at) "
            "VALUES ($1, $2, $3, false, false, $4, now(), now()) RETURNING id",
            str(uuid.uuid4()), email, password_hash, role_id,
        )
        admin_id = admin_row["id"]
    finally:
        await conn.close()

    resp = await gw.post("/api/v1/admin/auth/login", json={"email": email, "password": password})
    secret = None

    if resp.status_code == 200:
        # REQUIRE_ADMIN_MFA=false in this environment's .env (a documented
        # local-dev convenience, same category as the hardcoded "123456"
        # registration OTP) -- login succeeds immediately with no MFA
        # challenge at all.
        admin_auth = resp.json()
    else:
        # REQUIRE_ADMIN_MFA=true: real MFA-setup dance.
        assert resp.status_code == 403 and resp.json().get("detail") == "MFA_SETUP_REQUIRED", resp.text
        temp_token = resp.headers["X-Temp-Token"]

        resp = await gw.post(
            "/api/v1/admin/auth/mfa/setup",
            headers={"Authorization": f"Bearer {temp_token}"},
        )
        assert resp.status_code == 200, resp.text
        secret = resp.json()["secret"]

        totp_code = pyotp.TOTP(secret).now()
        resp = await gw.post(
            "/api/v1/admin/auth/mfa/verify",
            json={"totp_code": totp_code},
            headers={"Authorization": f"Bearer {temp_token}"},
        )
        assert resp.status_code == 200 and resp.json().get("enabled") is True, resp.text

        totp_code = pyotp.TOTP(secret).now()
        resp = await gw.post("/api/v1/admin/auth/login", json={
            "email": email, "password": password, "totp_code": totp_code,
        })
        assert resp.status_code == 200, resp.text
        admin_auth = resp.json()

    return {
        "admin_id": admin_id,
        "email": email,
        "access_token": admin_auth["access_token"],
        "totp_secret": secret,
        "password": password,
    }
