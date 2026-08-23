import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Callable

from sk_shared.redis_client import RedisClient
from sk_shared.events import (
    EVENT_DELIVERY_CONFIRMED, EVENT_DELIVERY_RETURNED, EVENT_DELIVERY_STATUS_CHANGED,
)

from src.config import settings
from src.services.notification_service import NotificationService

logger = logging.getLogger("event_listener")

# All channels the notification service subscribes to
SUBSCRIBED_CHANNELS = [
    # Auth
    "sk:events:auth.otp_requested",
    "sk:events:auth.otp_contract_sign",
    # KYC
    "sk:events:kyc.submitted",
    "sk:events:kyc.approved",
    "sk:events:kyc.rejected",
    "sk:events:kyc.waitlisted",
    "sk:events:kyc.documents_needed",   # NS integration gap
    # Credit
    "sk:events:credit.assessed.approved",
    "sk:events:credit.assessed.rejected",
    "sk:events:credit.limit_increased",
    "sk:events:credit.limit_changed",    # NS integration gap
    # Product / Order
    "sk:events:product.extracted",
    "sk:events:order.offer_ready",
    "sk:events:order.vcn_issued",
    "sk:events:order.checkout_completed",
    "sk:events:order.checkout_failed",
    "sk:events:order.cancelled",         # NS integration gap
    # Contracts
    "sk:events:contract.wakalah_ready",
    "sk:events:contract.murabaha_ready",
    "sk:events:contract.signed",
    # Payments
    "sk:events:payment.down_payment_initiated",
    "sk:events:payment.down_payment_confirmed",
    "sk:events:payment.down_payment_failed",
    "sk:events:payment.failed",          # NS integration gap (auto-debit)
    # Delivery
    f"sk:events:{EVENT_DELIVERY_STATUS_CHANGED}",
    f"sk:events:{EVENT_DELIVERY_CONFIRMED}",
    f"sk:events:{EVENT_DELIVERY_RETURNED}",
    # Billing
    "sk:events:billing.installment_paid",
    "sk:events:billing.installment_failed",
    "sk:events:billing.late_fee_applied",
    "sk:events:billing.late_fee_charity_allocated",
    "sk:events:billing.loan_fully_repaid",
    "sk:events:billing.installment_overdue",  # NS-BL-05: overdue alerts
    # VCN
    "sk:events:vcn.expired",             # NS integration gap
]

# Events for which a None return from the handler is INTENTIONAL (handled elsewhere).
# All other events with a None result will be sent to DLQ for investigation.
_SILENT_DROP_EVENTS: frozenset[str] = frozenset({
    "delivery.status_changed",  # Handled directly by tracking_service
})

# Singleton health state (read by health endpoint)
listener_state = {
    "running": False,
    "subscribed_channels": 0,
    "last_event_at": None,
    "error": None,
}


# ── Per-event payload extractors ─────────────────────────────────────────────
# Each returns (user_id, template_vars, idempotency_key, source_reference) or None

def _extract_kyc_approved(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return (
        user_id,
        {"user_name": payload.get("user_name", "Customer"), "credit_limit": str(payload.get("credit_limit", ""))},
        f"kyc-approved-user-{user_id}",
        f"kyc_application:{payload.get('kyc_id', '')}",
    )

def _extract_kyc_rejected(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return (
        user_id,
        {"user_name": payload.get("user_name", "Customer"), "rejection_reason": payload.get("reason", "requirements not met")},
        f"kyc-rejected-user-{user_id}-{payload.get('kyc_id', '')}",
        f"kyc_application:{payload.get('kyc_id', '')}",
    )

def _extract_down_payment_confirmed(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    order_id = payload.get("order_id")
    if not user_id or not order_id:
        return None
    return (
        user_id,
        {
            "amount": str(payload.get("amount", "")),
            "order_id": str(order_id),
            "product_description": payload.get("product_description", "your order"),
        },
        f"down-payment-confirmed-order-{order_id}",
        f"order:{order_id}",
    )

def _extract_installment_paid(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    installment_id = payload.get("installment_id")
    order_id = payload.get("order_id")
    if not user_id or not installment_id:
        return None
    return (
        user_id,
        {
            "amount": str(payload.get("amount", "")),
            "installment_number": str(payload.get("installment_number", "")),
            "total_installments": str(payload.get("total_installments", "")),
            "remaining_amount": str(payload.get("remaining_amount", "")),
        },
        f"installment-paid-{installment_id}",
        f"order:{order_id}",
    )

def _extract_late_fee_applied(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "fee_amount": str(payload.get("fee_amount", "")),
            "days_overdue": str(payload.get("days_overdue", "")),
            "order_id": str(payload.get("order_id", "")),
            "charity_org": settings.CHARITY_ORGANIZATION_NAME,
            "fee_disclosure": "These are actual administrative costs only, not interest (riba). 100% will be donated to charity.",
        },
        f"late-fee-applied-{payload.get('late_fee_id', payload.get('order_id', ''))}",
        f"order:{payload.get('order_id', '')}",
    )

def _extract_delivery_confirmed(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id") or payload.get("order_user_id")
    order_id = payload.get("order_id")
    if not user_id or not order_id:
        return None
    return (
        user_id,
        {
            "order_id": str(order_id),
            "product_description": payload.get("product_description", "your order"),
            "courier": payload.get("courier", ""),
            "tracking_number": payload.get("tracking_number", ""),
        },
        f"delivery-confirmed-order-{order_id}",
        f"order:{order_id}",
    )

def _extract_credit_approved(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "credit_limit": str(payload.get("credit_limit", "")),
            "risk_band": payload.get("risk_band", ""),
        },
        f"credit-approved-user-{user_id}-{payload.get('assessment_id', '')}",
        f"credit_assessment:{payload.get('assessment_id', '')}",
    )

def _extract_contract_signed(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    order_id = payload.get("order_id")
    if not user_id or not order_id:
        return None
    return (
        user_id,
        {
            "order_id": str(order_id),
            "cost_price": str(payload.get("cost_price", "")),
            "profit_amount": str(payload.get("profit_amount", "")),
            "total_amount": str(payload.get("total_amount", "")),
            "installment_count": str(payload.get("installment_count", "")),
            "down_payment": str(payload.get("down_payment", "")),
        },
        f"contract-signed-order-{order_id}",
        f"order:{order_id}",
    )

def _extract_loan_repaid(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    order_id = payload.get("order_id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "total_paid": str(payload.get("total_paid", "")),
            "order_id": str(order_id or ""),
            "product_description": payload.get("product_description", "your purchase"),
        },
        f"loan-repaid-order-{order_id}",
        f"order:{order_id}",
    )

# ── New integration event extractors (Section 6.4 gaps) ─────────────────────

def _extract_order_cancelled(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    order_id = payload.get("order_id")
    if not user_id or not order_id:
        return None
    return (
        user_id,
        {
            "order_id": str(order_id),
            "reason": payload.get("reason", ""),
            "product_description": payload.get("product_description", "your order"),
        },
        f"order-cancelled-{order_id}",
        f"order:{order_id}",
    )

def _extract_vcn_expired(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    vcn_id = payload.get("vcn_id") or payload.get("id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "vcn_last4": str(payload.get("last4", "****")),
            "order_id": str(payload.get("order_id", "")),
        },
        f"vcn-expired-{vcn_id}-user-{user_id}",
        f"vcn:{vcn_id}",
    )

def _extract_payment_failed(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    payment_id = payload.get("payment_id") or payload.get("installment_id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "amount": str(payload.get("amount", "")),
            "order_id": str(payload.get("order_id", "")),
            "failure_reason": payload.get("failure_reason", "payment could not be processed"),
        },
        f"payment-failed-{payment_id}-user-{user_id}",
        f"payment:{payment_id}",
    )

def _extract_kyc_documents_needed(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "user_name": payload.get("user_name", "Customer"),
            "required_docs": ", ".join(payload.get("required_documents", [])) or "requested documents",
            "kyc_id": str(payload.get("kyc_id", "")),
        },
        f"kyc-docs-needed-user-{user_id}-{payload.get('kyc_id', '')}",
        f"kyc:{payload.get('kyc_id', '')}",
    )

def _extract_credit_limit_changed(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    if not user_id:
        return None
    return (
        user_id,
        {
            "new_limit": str(payload.get("new_limit", "")),
            "old_limit": str(payload.get("old_limit", "")),
            "change_direction": "increased" if payload.get("new_limit", 0) > payload.get("old_limit", 0) else "adjusted",
        },
        f"credit-limit-changed-user-{user_id}-{payload.get('timestamp', '')}",
        f"credit:{user_id}",
    )


def _extract_billing_installment_overdue(payload: dict) -> Optional[Tuple]:
    user_id = payload.get("user_id")
    installment_id = payload.get("installment_id")
    if not user_id or not installment_id:
        return None
    return (
        user_id,
        {
            "installment_id": str(installment_id),
            "order_id": str(payload.get("order_id", "")),
            "amount": str(payload.get("amount", "")),
            "days_overdue": str(payload.get("days_overdue", 0)),
        },
        f"billing-installment-overdue-{installment_id}",
        f"order:{payload.get('order_id', '')}",
    )


# ── Master event handler registry ────────────────────────────────────────────
EVENT_HANDLERS: dict[str, Callable] = {
    "kyc.approved": _extract_kyc_approved,
    "kyc.rejected": _extract_kyc_rejected,
    "kyc.submitted": lambda p: (p.get("user_id"), {"user_name": p.get("user_name", "Customer")},
                                 f"kyc-submitted-{p.get('user_id')}", f"kyc:{p.get('kyc_id', '')}"),
    "kyc.documents_needed": _extract_kyc_documents_needed,
    "credit.assessed.approved": _extract_credit_approved,
    "credit.assessed.rejected": lambda p: (p.get("user_id"), {"rejection_reasons": ", ".join(p.get("reasons", []))},
                                            f"credit-rejected-{p.get('assessment_id', p.get('user_id'))}", None),
    "credit.limit_changed": _extract_credit_limit_changed,
    "payment.down_payment_confirmed": _extract_down_payment_confirmed,
    "payment.down_payment_failed": lambda p: (p.get("user_id"), {"amount": str(p.get("amount", "")), "order_id": str(p.get("order_id", ""))},
                                               f"dp-failed-order-{p.get('order_id')}", f"order:{p.get('order_id')}"),
    "payment.failed": _extract_payment_failed,
    "contract.signed": _extract_contract_signed,
    "billing.installment_paid": _extract_installment_paid,
    "billing.installment_failed": lambda p: (p.get("user_id"), {"amount": str(p.get("amount", "")), "order_id": str(p.get("order_id", ""))},
                                              f"billing-failed-{p.get('installment_id', '')}", f"order:{p.get('order_id', '')}") if p.get("user_id") else None,
    "billing.installment_overdue": _extract_billing_installment_overdue,
    "billing.late_fee_applied": _extract_late_fee_applied,
    "billing.loan_fully_repaid": _extract_loan_repaid,
    "billing.late_fee_charity_allocated": lambda p: (p.get("user_id"),
                                                      {"fee_amount": str(p.get("fee_amount", "")), "charity_org": settings.CHARITY_ORGANIZATION_NAME},
                                                      f"charity-allocated-{p.get('late_fee_id', '')}",
                                                      f"order:{p.get('order_id', '')}"),
    "delivery.confirmed": _extract_delivery_confirmed,
    "delivery.returned": lambda p: (p.get("user_id") or p.get("order_user_id"),
                                     {"order_id": str(p.get("order_id", "")), "tracking_number": p.get("tracking_number", "")},
                                     f"delivery-returned-order-{p.get('order_id')}", f"order:{p.get('order_id')}"),
    "delivery.status_changed": lambda p: None,  # Handled by tracking_service directly
    "order.checkout_completed": lambda p: (p.get("user_id"), {"order_id": str(p.get("order_id", "")), "merchant": p.get("merchant_name", "the merchant")},
                                            f"checkout-completed-order-{p.get('order_id')}", f"order:{p.get('order_id')}"),
    "order.cancelled": _extract_order_cancelled,
    "vcn.expired": _extract_vcn_expired,
}


async def _handle_message(event_type: str, envelope: dict, notification_service, redis=None) -> None:
    """
    Dispatch an incoming event to the appropriate notification handler.

    NS-BL-04: A None result from a handler is ambiguous:
      - For events in _SILENT_DROP_EVENTS (e.g. delivery.status_changed), None is
        intentional — the event is handled elsewhere.
      - For all other events, None means required fields were missing from the payload.
        These are pushed to the DLQ for investigation rather than silently dropped.
    """
    payload = envelope.get("payload", {})
    handler = EVENT_HANDLERS.get(event_type)

    if handler is None:
        logger.debug("No handler for event type", extra={"event_type": event_type})
        return

    result = handler(payload)

    if result is None:
        if event_type not in _SILENT_DROP_EVENTS:
            # NS-BL-04: Non-intentional None — push to DLQ for operator review
            logger.warning(
                "Event payload extraction returned None — missing required fields",
                extra={"event_type": event_type, "payload_keys": list(payload.keys())},
            )
            if redis is not None:
                try:
                    await redis.lpush(
                        settings.NOTIFICATION_DLQ_KEY,
                        json.dumps({
                            "type": "event_extraction_failure",
                            "event_type": event_type,
                            "envelope": envelope,
                            "failed_at": datetime.now(timezone.utc).isoformat(),
                        }),
                    )
                except Exception as dlq_err:
                    logger.error("Failed to push extraction failure to DLQ", extra={"error": str(dlq_err)})
        return

    user_id, template_vars, idempotency_key, source_reference = result
    if not user_id:
        logger.warning("Missing user_id in event payload", extra={"event_type": event_type})
        return

    try:
        await notification_service.create_notification(
            user_id=user_id,
            event_type=event_type,
            template_vars=template_vars,
            idempotency_key=idempotency_key,
            source_reference=source_reference,
        )
    except Exception as e:
        logger.error(
            "Failed to create notification from event",
            extra={"event_type": event_type, "user_id": user_id, "error": str(e)},
        )


async def listen_to_redis_events(app):
    redis: RedisClient = app.state.redis
    db_factory = app.state.db_factory

    listener_state["running"] = True
    while True:
        try:
            pubsub = redis.redis.pubsub()
            await pubsub.subscribe(*SUBSCRIBED_CHANNELS)
            listener_state["subscribed_channels"] = len(SUBSCRIBED_CHANNELS)
            listener_state["error"] = None
            logger.info("Event listener subscribed", extra={"channels": len(SUBSCRIBED_CHANNELS)})

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                listener_state["last_event_at"] = datetime.now(timezone.utc).isoformat()

                try:
                    envelope = json.loads(message["data"])
                    channel = message["channel"].decode("utf-8") if isinstance(message["channel"], bytes) else message["channel"]
                    event_type = channel.split(":", 2)[-1]
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning("Failed to parse event message", extra={"error": str(e)})
                    continue

                async with db_factory() as db:
                    ns = NotificationService(db=db, redis=redis)
                    await _handle_message(event_type, envelope, ns, redis=redis)

        except asyncio.CancelledError:
            listener_state["running"] = False
            return
        except Exception as e:
            listener_state["error"] = str(e)
            logger.error("Event listener crashed, restarting in 5s", extra={"error": str(e)})
            await asyncio.sleep(5)

async def start_event_listener(app):
    """
    Start the Redis pub/sub listener as a background asyncio task.
    Reconnects automatically on connection loss.
    """
    return asyncio.create_task(listen_to_redis_events(app))
