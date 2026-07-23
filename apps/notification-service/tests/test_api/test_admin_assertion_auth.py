"""
Hardening tests for notification-service's admin auth dependencies.

Previously `require_operations_manager` / `require_permissions` trusted raw,
caller-supplied `X-Admin-Role` / `X-Admin-Permissions` headers with zero
cryptographic verification -- any direct caller could set those headers
themselves and get full admin access to admin_notifications (read all users'
notifications, purge/retry DLQ) and admin_tracking.

These tests verify the fix: admin identity/role/permissions must now arrive as
a short-lived, HMAC-signed assertion (sk_shared.security.create_signed_assertion,
verified via verify_signed_assertion) in the `X-Admin-Assertion` header, and the
old raw-header spoof no longer works on its own.
"""
import time

import pytest

from sk_shared.security import create_signed_assertion
from src.config import settings

TRACKING_ISSUES_URL = "/api/v1/admin/tracking/issues"
NOTIFICATIONS_STATS_URL = "/api/v1/admin/notifications/stats"


def _assertion(claims: dict, secret: str | None = None, ttl_seconds: int = 60) -> str:
    return create_signed_assertion(claims, secret=secret or settings.INTERNAL_API_KEY, ttl_seconds=ttl_seconds)


@pytest.mark.asyncio
async def test_valid_signed_assertion_grants_operations_manager_access(client):
    assertion = _assertion({"admin_id": 1, "role": "operations_manager", "permissions": ["all_actions"]})
    response = await client.get(TRACKING_ISSUES_URL, headers={"x-admin-assertion": assertion})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_valid_signed_assertion_grants_permission_based_access(client):
    assertion = _assertion({"admin_id": 1, "role": "cs_agent", "permissions": ["admin:notifications:read"]})
    response = await client.get(NOTIFICATIONS_STATS_URL, headers={"x-admin-assertion": assertion})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_assertion_is_rejected(client):
    response = await client.get(TRACKING_ISSUES_URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"

    response = await client.get(NOTIFICATIONS_STATS_URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"


@pytest.mark.asyncio
async def test_tampered_assertion_is_rejected(client):
    assertion = _assertion({"admin_id": 1, "role": "cs_agent", "permissions": []})
    encoded, signature = assertion.rsplit(".", 1)

    # Forge a higher-privileged payload but keep the original (now-mismatched) signature.
    import base64
    import json

    forged_bytes = json.dumps(
        {"role": "operations_manager", "permissions": ["all_actions"], "iat": 0, "exp": int(time.time()) + 60}
    ).encode()
    forged_encoded = base64.urlsafe_b64encode(forged_bytes).decode().rstrip("=")
    tampered = f"{forged_encoded}.{signature}"

    response = await client.get(TRACKING_ISSUES_URL, headers={"x-admin-assertion": tampered})
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_INVALID_ASSERTION"


@pytest.mark.asyncio
async def test_assertion_signed_with_wrong_secret_is_rejected(client):
    assertion = _assertion(
        {"admin_id": 1, "role": "operations_manager", "permissions": ["all_actions"]},
        secret="not-the-real-secret",
    )
    response = await client.get(TRACKING_ISSUES_URL, headers={"x-admin-assertion": assertion})
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_INVALID_ASSERTION"


@pytest.mark.asyncio
async def test_expired_assertion_is_rejected(client):
    assertion = _assertion(
        {"admin_id": 1, "role": "operations_manager", "permissions": ["all_actions"]},
        ttl_seconds=-1,
    )
    response = await client.get(TRACKING_ISSUES_URL, headers={"x-admin-assertion": assertion})
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_INVALID_ASSERTION"


@pytest.mark.asyncio
async def test_spoofed_raw_admin_role_header_alone_no_longer_grants_access(client):
    """The exact vulnerability being fixed: previously setting X-Admin-Role directly
    was sufficient. Now it must be ignored in favor of a verified assertion."""
    response = await client.get(TRACKING_ISSUES_URL, headers={"x-admin-role": "operations_manager"})
    assert response.status_code == 403

    response = await client.get(
        NOTIFICATIONS_STATS_URL,
        headers={"x-admin-permissions": "admin:notifications:read,all_actions"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_assertion_with_insufficient_permissions_is_rejected(client):
    assertion = _assertion({"admin_id": 1, "role": "cs_agent", "permissions": ["some:other:permission"]})
    response = await client.get(NOTIFICATIONS_STATS_URL, headers={"x-admin-assertion": assertion})
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_INSUFFICIENT_PERMISSIONS"


@pytest.mark.asyncio
async def test_assertion_with_wrong_role_is_rejected_for_operations_manager_route(client):
    assertion = _assertion({"admin_id": 1, "role": "cs_agent", "permissions": ["all_actions"]})
    response = await client.get(TRACKING_ISSUES_URL, headers={"x-admin-assertion": assertion})
    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN"
