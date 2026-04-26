import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sk_shared.models.payment import Installment, InstallmentStatus
from sk_shared.models.order import Order
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.services.notification_service import NotificationService

logger = logging.getLogger("reminder_worker")

async def fire_installment_reminders() -> dict:
    """
    Find all installments due in [1, 3] days and create reminder notifications.
    Idempotency key prevents duplicate reminders for the same installment+day window.
    """
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    stats = {"processed": 0, "created": 0, "skipped_duplicate": 0, "errors": 0}

    for days_before in settings.REMINDER_DAYS_BEFORE:
        target_date = (datetime.now(timezone.utc) + timedelta(days=days_before)).date()
        event_type = f"billing.installment_due_d{days_before}"

        async with SessionLocal() as db:
            # Query due installments for this window
            # Join with Order to get user_id and product_description
            query = select(Installment, Order).join(Order, Order.id == Installment.order_id).where(
                Installment.due_date == target_date,
                Installment.status == InstallmentStatus.PENDING,
            )
            
            rows = (await db.execute(query)).all()

            ns = NotificationService(db=db, redis=redis)

            for installment, order in rows:
                stats["processed"] += 1
                idempotency_key = f"reminder-d{days_before}-installment-{installment.id}-{target_date}"

                try:
                    await ns.create_notification(
                        user_id=order.user_id,
                        event_type=event_type,
                        template_vars={
                            "installment_amount": str(installment.amount),
                            "due_date": str(installment.due_date),
                            "order_description": order.product_description or f"Order #{order.id}",
                            "installment_number": str(installment.installment_number),
                            "total_installments": str(installment.total_installments or ""),
                        },
                        idempotency_key=idempotency_key,
                        source_reference=f"installment:{installment.id}",
                    )
                    stats["created"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Failed to create reminder", extra={
                        "installment_id": installment.id,
                        "days_before": days_before,
                        "error": str(e),
                    })

    logger.info("Reminder sweep complete", extra=stats)
    return stats

if __name__ == "__main__":
    asyncio.run(fire_installment_reminders())
