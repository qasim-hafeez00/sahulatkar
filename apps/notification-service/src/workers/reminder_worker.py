import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sk_shared.models.payment import Installment, Loan
from sk_shared.models.order import Order
from sk_shared.database import SessionLocal
from sk_shared.redis_client import get_redis_client
from src.config import settings
from src.services.notification_service import NotificationService

logger = logging.getLogger("reminder_worker")

# Days-after-due used for overdue escalation notifications
_OVERDUE_THRESHOLDS = [1, 7, 14]  # D+1, D+7, D+14 after due date


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
            query = (
                select(Installment, Loan, Order)
                .join(Loan, Loan.id == Installment.loan_id)
                .join(Order, Order.id == Loan.order_id)
                .where(
                    Installment.due_date == target_date,
                    Installment.status == "pending",
                )
            )

            rows = (await db.execute(query)).all()
            ns = NotificationService(db=db, redis=redis)

            for installment, loan, order in rows:
                stats["processed"] += 1
                idempotency_key = f"reminder-d{days_before}-installment-{installment.id}-{target_date}"

                try:
                    await ns.create_notification(
                        user_id=order.user_id,
                        event_type=event_type,
                        template_vars={
                            "installment_amount": str(installment.total_amount),
                            "due_date": str(installment.due_date),
                            "order_description": order.product_description or f"Order #{order.id}",
                            "installment_number": str(installment.installment_number),
                            "total_installments": str(loan.installment_count),
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

    # extra={"stats": stats} rather than extra=stats: stats's "created" key
    # collides with LogRecord's own builtin "created" (timestamp) attribute,
    # which makes logging.info() raise KeyError on every call.
    logger.info("Reminder sweep complete", extra={"stats": stats})
    return stats


async def fire_overdue_reminders() -> dict:
    """
    NS-BL-05: Fire overdue notifications for installments that have ALREADY passed
    their due date without payment. Sends escalating notifications at D+1, D+7, D+14.

    Complements fire_installment_reminders() which only covers upcoming payments.
    The billing.installment_overdue event gap identified in section 6.4 is addressed
    here: the reminder_worker publishes these events since no other service does.
    Idempotency keys: overdue-d{N}-installment-{id}-{check_date}
    """
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    today = datetime.now(timezone.utc).date()
    stats = {"processed": 0, "created": 0, "skipped_duplicate": 0, "errors": 0}

    for days_overdue in _OVERDUE_THRESHOLDS:
        # Target the exact day that is N days past the due date
        target_date = today - timedelta(days=days_overdue)
        event_type = f"billing.installment_overdue_d{days_overdue}"

        async with SessionLocal() as db:
            query = (
                select(Installment, Order)
                .join(Loan, Loan.id == Installment.loan_id)
                .join(Order, Order.id == Loan.order_id)
                .where(
                    Installment.due_date == target_date,
                    # Still unpaid — overdue status or pending past due date
                    Installment.status.in_(["overdue", "pending"]),
                )
            )

            rows = (await db.execute(query)).all()
            ns = NotificationService(db=db, redis=redis)

            for installment, order in rows:
                stats["processed"] += 1
                # Idempotency: fire once per installment per overdue threshold per check date
                idempotency_key = f"overdue-d{days_overdue}-installment-{installment.id}-{today}"

                try:
                    await ns.create_notification(
                        user_id=order.user_id,
                        event_type=event_type,
                        template_vars={
                            "installment_amount": str(installment.total_amount),
                            "due_date": str(installment.due_date),
                            "days_overdue": str(days_overdue),
                            "order_description": order.product_description or f"Order #{order.id}",
                            "installment_number": str(installment.installment_number),
                        },
                        idempotency_key=idempotency_key,
                        source_reference=f"installment:{installment.id}",
                    )
                    stats["created"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Failed to create overdue reminder", extra={
                        "installment_id": installment.id,
                        "days_overdue": days_overdue,
                        "error": str(e),
                    })

    logger.info("Overdue reminder sweep complete", extra={"stats": stats})
    return stats


if __name__ == "__main__":
    async def _main():
        upcoming_stats = await fire_installment_reminders()
        overdue_stats = await fire_overdue_reminders()
        logger.info("All reminder sweeps complete", extra={
            "upcoming": upcoming_stats,
            "overdue": overdue_stats,
        })

    asyncio.run(_main())
