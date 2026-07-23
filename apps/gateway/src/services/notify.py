import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.notification import Notification

logger = logging.getLogger("gateway")


async def notify(
    db: AsyncSession,
    user_id: int,
    category: str,
    title: str,
    body: str,
    source_event: str,
    source_reference: str | None = None,
) -> None:
    """Create an in-app notification row for the customer inbox.

    Runs in a savepoint so a failure here never rolls back the caller's
    surrounding transaction -- this is a best-effort side effect, not a
    critical path.
    """
    try:
        async with db.begin_nested():
            db.add(
                Notification(
                    user_id=user_id,
                    source_event=source_event,
                    source_reference=source_reference,
                    category=category,
                    priority="normal",
                    title=title,
                    body=body,
                    status="delivered",
                    idempotency_key=f"{source_event}:{source_reference or user_id}:{uuid.uuid4().hex[:12]}",
                    channels_requested=["in_app"],
                    template_vars={},
                )
            )
    except Exception:
        logger.warning("Failed to create in-app notification for user %s (%s)", user_id, source_event, exc_info=True)
