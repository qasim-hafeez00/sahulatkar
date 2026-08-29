import json

import pytest

from sk_shared.models.auth import User
from sk_shared.models.notification import DispatchStatus, Notification, NotificationDispatch
from sk_shared.security import create_signed_assertion

from src.config import settings
from src.main import app


async def _seed_user(session, user_id: int = 42) -> User:
    user = User(id=user_id, phone=f"+92300{user_id:07d}", status="active")
    session.add(user)
    await session.commit()
    return user


async def _seed_notification(
    session,
    user_id: int = 42,
    idempotency_key: str = "notif-admin-1",
    status: str = "delivered",
) -> Notification:
    notification = Notification(
        user_id=user_id,
        source_event="payment.down_payment_confirmed",
        category="payment",
        priority="high",
        title="Payment confirmed",
        body="Your down payment was received.",
        is_read=False,
        status=status,
        idempotency_key=idempotency_key,
        channels_requested=["sms"],
        template_vars={},
    )
    session.add(notification)
    await session.commit()
    await session.refresh(notification)
    return notification


def _assertion_with_permissions(permissions: list[str]) -> dict[str, str]:
    """Build a validly-signed admin assertion carrying arbitrary permissions,
    used to exercise the 'authenticated but insufficient permissions' path."""
    assertion = create_signed_assertion(
        {"admin_id": 2, "role": "operations_manager", "permissions": permissions},
        secret=settings.INTERNAL_API_KEY,
    )
    return {"x-admin-assertion": assertion}


# ── GET /api/v1/admin/notifications/stats ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_notification_stats_happy_path(client, db_session, admin_header):
    await _seed_user(db_session, user_id=42)
    await _seed_notification(db_session, idempotency_key="notif-stats-1", status="delivered")
    await _seed_notification(db_session, idempotency_key="notif-stats-2", status="delivered")
    await _seed_notification(db_session, idempotency_key="notif-stats-3", status="failed")

    response = await client.get("/api/v1/admin/notifications/stats", headers=admin_header)

    assert response.status_code == 200
    body = response.json()
    assert body["notifications"]["delivered"] == 2
    assert body["notifications"]["failed"] == 1


@pytest.mark.asyncio
async def test_get_notification_stats_requires_admin_assertion(client):
    response = await client.get("/api/v1/admin/notifications/stats")

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"


@pytest.mark.asyncio
async def test_get_notification_stats_forbidden_without_read_permission(client):
    headers = _assertion_with_permissions(["admin:tracking:read"])

    response = await client.get("/api/v1/admin/notifications/stats", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_INSUFFICIENT_PERMISSIONS"


# ── GET /api/v1/admin/notifications/dlq ─────────────────────────────────────


@pytest.mark.asyncio
async def test_list_dlq_items_happy_path(client, admin_header):
    dlq_item = {"notification_id": 7, "channel": "sms", "reason": "provider_timeout"}
    await app.state.redis.rpush(settings.NOTIFICATION_DLQ_KEY, json.dumps(dlq_item))

    response = await client.get("/api/v1/admin/notifications/dlq", headers=admin_header)

    assert response.status_code == 200
    body = response.json()
    assert body == [dlq_item]


@pytest.mark.asyncio
async def test_list_dlq_items_requires_admin_assertion(client):
    response = await client.get("/api/v1/admin/notifications/dlq")

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"


@pytest.mark.asyncio
async def test_list_dlq_items_forbidden_without_write_permission(client):
    headers = _assertion_with_permissions(["admin:notifications:read"])

    response = await client.get("/api/v1/admin/notifications/dlq", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_INSUFFICIENT_PERMISSIONS"


# ── POST /api/v1/admin/notifications/retry/{notification_id} ───────────────


@pytest.mark.asyncio
async def test_retry_notification_happy_path(client, db_session, admin_header):
    await _seed_user(db_session, user_id=42)
    notification = await _seed_notification(db_session, idempotency_key="notif-retry-1", status="failed")
    dispatch = NotificationDispatch(
        notification_id=notification.id,
        channel="sms",
        status=DispatchStatus.DLQ.value,
        attempt_count=5,
    )
    db_session.add(dispatch)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/admin/notifications/retry/{notification.id}", headers=admin_header
    )

    assert response.status_code == 200
    assert response.json() == {"status": "re-queued"}

    await db_session.refresh(notification)
    assert notification.status == "queued"

    await db_session.refresh(dispatch)
    assert dispatch.status == "pending"
    assert dispatch.attempt_count == 0

    queued_ids = await app.state.redis.lrange(settings.NOTIFICATION_QUEUE_KEY, 0, -1)
    assert str(notification.id).encode() in queued_ids


@pytest.mark.asyncio
async def test_retry_notification_not_found(client, admin_header):
    response = await client.post("/api/v1/admin/notifications/retry/999999", headers=admin_header)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_notification_requires_admin_assertion(client, db_session):
    await _seed_user(db_session, user_id=42)
    notification = await _seed_notification(db_session, idempotency_key="notif-retry-2", status="failed")

    response = await client.post(f"/api/v1/admin/notifications/retry/{notification.id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"

    await db_session.refresh(notification)
    assert notification.status == "failed"


# ── POST /api/v1/admin/notifications/dlq/retry-all ──────────────────────────


@pytest.mark.asyncio
async def test_retry_all_dlq_happy_path(client, db_session, admin_header):
    await _seed_user(db_session, user_id=42)
    notification = await _seed_notification(db_session, idempotency_key="notif-retry-all-1", status="failed")
    dispatch = NotificationDispatch(
        notification_id=notification.id,
        channel="sms",
        status=DispatchStatus.DLQ.value,
        attempt_count=5,
    )
    db_session.add(dispatch)
    await db_session.commit()

    dlq_item = {"notification_id": notification.id, "channel": "sms", "reason": "provider_timeout"}
    await app.state.redis.rpush(settings.NOTIFICATION_DLQ_KEY, json.dumps(dlq_item))

    response = await client.post("/api/v1/admin/notifications/dlq/retry-all", headers=admin_header)

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "requeued_count": 1}

    await db_session.refresh(dispatch)
    assert dispatch.status == "pending"

    remaining_dlq = await app.state.redis.lrange(settings.NOTIFICATION_DLQ_KEY, 0, -1)
    assert remaining_dlq == []


@pytest.mark.asyncio
async def test_retry_all_dlq_requires_admin_assertion(client):
    response = await client.post("/api/v1/admin/notifications/dlq/retry-all")

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"


# ── DELETE /api/v1/admin/notifications/dlq/purge ────────────────────────────


@pytest.mark.asyncio
async def test_purge_dlq_happy_path(client, admin_header):
    await app.state.redis.rpush(settings.NOTIFICATION_DLQ_KEY, json.dumps({"notification_id": 1}))

    response = await client.request(
        "DELETE", "/api/v1/admin/notifications/dlq/purge", headers=admin_header
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    remaining_dlq = await app.state.redis.lrange(settings.NOTIFICATION_DLQ_KEY, 0, -1)
    assert remaining_dlq == []


@pytest.mark.asyncio
async def test_purge_dlq_requires_admin_assertion(client):
    response = await client.request("DELETE", "/api/v1/admin/notifications/dlq/purge")

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN_ADMIN_NO_ASSERTION"
