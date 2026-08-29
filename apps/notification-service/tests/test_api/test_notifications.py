import pytest
from sqlalchemy import select

from sk_shared.models.auth import User
from sk_shared.models.notification import Notification


async def _seed_user(session, user_id: int = 42) -> User:
    user = User(id=user_id, phone=f"+92300{user_id:07d}", status="active")
    session.add(user)
    await session.commit()
    return user


async def _seed_notification(
    session,
    user_id: int = 42,
    idempotency_key: str = "notif-1",
    is_read: bool = False,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        source_event="payment.down_payment_confirmed",
        category="payment",
        priority="high",
        title="Payment confirmed",
        body="Your down payment was received.",
        is_read=is_read,
        status="delivered",
        idempotency_key=idempotency_key,
        channels_requested=["sms"],
        template_vars={},
    )
    session.add(notification)
    await session.commit()
    await session.refresh(notification)
    return notification


# ── GET /api/v1/notifications/ ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_notifications_returns_user_notifications(client, db_session, user_header):
    await _seed_user(db_session, user_id=42)
    await _seed_notification(db_session, user_id=42, idempotency_key="notif-list-1")

    response = await client.get("/api/v1/notifications/", headers=user_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["unread_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "Payment confirmed"
    assert body["items"][0]["source_event"] == "payment.down_payment_confirmed"


@pytest.mark.asyncio
async def test_list_notifications_scoped_to_authenticated_user(client, db_session, user_header):
    await _seed_user(db_session, user_id=42)
    await _seed_user(db_session, user_id=99)
    await _seed_notification(db_session, user_id=42, idempotency_key="notif-mine")
    await _seed_notification(db_session, user_id=99, idempotency_key="notif-other")

    response = await client.get("/api/v1/notifications/", headers=user_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Payment confirmed"


@pytest.mark.asyncio
async def test_list_notifications_requires_authentication(client):
    response = await client.get("/api/v1/notifications/")

    assert response.status_code == 401
    assert response.json()["detail"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_list_notifications_rejects_invalid_user_header(client):
    response = await client.get("/api/v1/notifications/", headers={"x-user-id": "not-a-number"})

    assert response.status_code == 401
    assert response.json()["detail"] == "INVALID_USER_CONTEXT"


# ── POST /api/v1/notifications/{id}/read ────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_notification_read_happy_path(client, db_session, user_header):
    await _seed_user(db_session, user_id=42)
    notification = await _seed_notification(db_session, user_id=42, idempotency_key="notif-read-1")

    response = await client.post(f"/api/v1/notifications/{notification.id}/read", headers=user_header)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    await db_session.refresh(notification)
    assert notification.is_read is True
    assert notification.read_at is not None


@pytest.mark.asyncio
async def test_mark_notification_read_requires_authentication(client, db_session):
    await _seed_user(db_session, user_id=42)
    notification = await _seed_notification(db_session, user_id=42, idempotency_key="notif-read-2")

    response = await client.post(f"/api/v1/notifications/{notification.id}/read")

    assert response.status_code == 401
    assert response.json()["detail"] == "UNAUTHENTICATED"

    refreshed = await db_session.scalar(select(Notification).where(Notification.id == notification.id))
    assert refreshed.is_read is False


@pytest.mark.asyncio
async def test_mark_notification_read_not_found_for_missing_notification(client, db_session, user_header):
    await _seed_user(db_session, user_id=42)

    response = await client.post("/api/v1/notifications/999999/read", headers=user_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "NOTIFICATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_mark_notification_read_not_found_for_other_users_notification(client, db_session, user_header):
    await _seed_user(db_session, user_id=42)
    await _seed_user(db_session, user_id=99)
    other_notification = await _seed_notification(db_session, user_id=99, idempotency_key="notif-not-mine")

    # Authenticated as user 42, but the notification belongs to user 99.
    response = await client.post(f"/api/v1/notifications/{other_notification.id}/read", headers=user_header)

    assert response.status_code == 404
    assert response.json()["detail"] == "NOTIFICATION_NOT_FOUND"

    refreshed = await db_session.scalar(select(Notification).where(Notification.id == other_notification.id))
    assert refreshed.is_read is False
