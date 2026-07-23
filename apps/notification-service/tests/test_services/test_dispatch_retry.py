"""
P1 regression: multi-channel notification retry must not be silently dropped
after a partial success, and a later retry attempt must never regress the
aggregate status of a notification that already delivered on another channel.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from sk_shared.models.auth import User
from sk_shared.models.notification import (
    DispatchStatus,
    Notification,
    NotificationDispatch,
    NotificationStatus,
)
from src.dispatchers.base import DispatchResult
from src.services.notification_service import DISPATCHERS, NotificationService


@pytest.mark.asyncio
async def test_retry_still_processes_pending_channel_after_other_channel_delivered(db_session, redis_mock):
    """SMS already delivered (notification.status == DELIVERED); email is still
    RETRYING. A retry re-enqueue for this notification_id must still attempt
    the email channel, not bail out early because the aggregate status looks
    'done'."""
    user = User(phone="+923001112222")
    db_session.add(user)
    await db_session.flush()

    notif = Notification(
        user_id=user.id,
        source_event="contract.signed",
        category="contract",
        title="Contract Signed",
        body="Your contract is signed",
        idempotency_key="retry-test-key-1",
        channels_requested=["sms", "email"],
        template_vars={"destination_email": "retry-test-1@example.com"},
        status=NotificationStatus.DELIVERED,
    )
    db_session.add(notif)
    await db_session.flush()

    sms_dispatch = NotificationDispatch(
        notification_id=notif.id, channel="sms", status=DispatchStatus.SENT, attempt_count=1,
    )
    email_dispatch = NotificationDispatch(
        notification_id=notif.id, channel="email", status=DispatchStatus.RETRYING, attempt_count=1,
        next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add_all([sms_dispatch, email_dispatch])
    await db_session.commit()

    original_email_send = DISPATCHERS["email"].send
    DISPATCHERS["email"].send = AsyncMock(
        return_value=DispatchResult(success=False, failure_reason="TEMPORARY_PROVIDER_ERROR", should_retry=True)
    )
    try:
        svc = NotificationService(db=db_session, redis=redis_mock)
        await svc.dispatch_notification(notif.id)
    finally:
        DISPATCHERS["email"].send = original_email_send

    await db_session.refresh(email_dispatch)
    # The bug: dispatch_notification used to return immediately because
    # notification.status was already DELIVERED, leaving attempt_count at 1
    # forever. It must now have been retried (attempt_count incremented).
    assert email_dispatch.attempt_count == 2
    assert email_dispatch.status == DispatchStatus.RETRYING


@pytest.mark.asyncio
async def test_retry_failure_on_other_channel_does_not_regress_delivered_status(db_session, redis_mock):
    """A previously-successful channel (sms, status=sent) must keep the
    notification's aggregate status as DELIVERED even if a later retry of a
    different channel (email) fails again."""
    user = User(phone="+923001112223")
    db_session.add(user)
    await db_session.flush()

    notif = Notification(
        user_id=user.id,
        source_event="contract.signed",
        category="contract",
        title="Contract Signed",
        body="Your contract is signed",
        idempotency_key="retry-test-key-2",
        channels_requested=["sms", "email"],
        template_vars={"destination_email": "retry-test-2@example.com"},
        status=NotificationStatus.DELIVERED,
    )
    db_session.add(notif)
    await db_session.flush()

    sms_dispatch = NotificationDispatch(
        notification_id=notif.id, channel="sms", status=DispatchStatus.SENT, attempt_count=1,
    )
    email_dispatch = NotificationDispatch(
        notification_id=notif.id, channel="email", status=DispatchStatus.RETRYING, attempt_count=3,
        next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add_all([sms_dispatch, email_dispatch])
    await db_session.commit()

    original_email_send = DISPATCHERS["email"].send
    DISPATCHERS["email"].send = AsyncMock(
        return_value=DispatchResult(success=False, failure_reason="PERMANENT_FAILURE", should_retry=False)
    )
    try:
        svc = NotificationService(db=db_session, redis=redis_mock)
        await svc.dispatch_notification(notif.id)
    finally:
        DISPATCHERS["email"].send = original_email_send

    await db_session.refresh(notif)
    await db_session.refresh(email_dispatch)
    assert email_dispatch.status == DispatchStatus.FAILED
    # Must remain DELIVERED — SMS already succeeded, even though email's last
    # retry attempt just failed permanently.
    assert notif.status == NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_notification_marked_failed_only_when_no_channel_ever_succeeds(db_session, redis_mock):
    user = User(phone="+923001112224")
    db_session.add(user)
    await db_session.flush()

    notif = Notification(
        user_id=user.id,
        source_event="contract.signed",
        category="contract",
        title="Contract Signed",
        body="Your contract is signed",
        idempotency_key="retry-test-key-3",
        channels_requested=["email"],
        template_vars={"destination_email": "retry-test-3@example.com"},
        status=NotificationStatus.DISPATCHING,
    )
    db_session.add(notif)
    await db_session.flush()

    email_dispatch = NotificationDispatch(
        notification_id=notif.id, channel="email", status=DispatchStatus.RETRYING, attempt_count=3,
        next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add(email_dispatch)
    await db_session.commit()

    original_email_send = DISPATCHERS["email"].send
    DISPATCHERS["email"].send = AsyncMock(
        return_value=DispatchResult(success=False, failure_reason="PERMANENT_FAILURE", should_retry=False)
    )
    try:
        svc = NotificationService(db=db_session, redis=redis_mock)
        await svc.dispatch_notification(notif.id)
    finally:
        DISPATCHERS["email"].send = original_email_send

    await db_session.refresh(notif)
    assert notif.status == NotificationStatus.FAILED
