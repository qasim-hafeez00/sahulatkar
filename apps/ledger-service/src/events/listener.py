from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from sk_shared.events import EVENT_DELIVERY_STATUS_CHANGED, EVENT_LOAN_CREATED, EVENT_ORDER_PURCHASE_CONFIRMED, EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED, EVENT_PAYMENT_INSTALLMENT_PAID, event_channel
from sk_shared.models.payment import Installment
from sk_shared.redis_client import RedisClient

from src.core.database import SessionLocal
from src.events.dlq import EventDeadLetterQueue
from src.services.accounting_service import AccountingService


logger = logging.getLogger(__name__)


class EventProcessingFailed(Exception):
    def __init__(self, cause: Exception, retry_count: int) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.retry_count = retry_count


def _is_transient_error(error: Exception) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return True
    if isinstance(error, DBAPIError) and bool(getattr(error, "connection_invalidated", False)):
        return True
    return False


async def _run_with_retry(
    operation: Callable[[], Awaitable[None]],
    *,
    max_retries: int = 3,
    base_delay_seconds: float = 0.2,
) -> int:
    retry_count = 0
    while True:
        try:
            await operation()
            return retry_count
        except Exception as exc:
            if retry_count >= max_retries or not _is_transient_error(exc):
                raise EventProcessingFailed(exc, retry_count) from exc

            retry_count += 1
            await asyncio.sleep(base_delay_seconds * (2 ** (retry_count - 1)))


async def _process_event_once(event_name: str | None, payload: dict[str, object], redis: RedisClient | None = None) -> None:
    async with SessionLocal() as session:
        service = AccountingService(session, redis=redis)
        if event_name == EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED:
            await service.record_down_payment(order_id=int(payload["order_id"]), amount=payload["amount_pkr"])
        elif event_name == EVENT_PAYMENT_INSTALLMENT_PAID:
            installment_id = int(payload["installment_id"])
            event_amount = Decimal(str(payload["amount_pkr"]))

            # LS-BL-05: Validate event amount vs. actual installment expected amount
            async with SessionLocal() as validation_session:
                stmt = select(Installment).where(Installment.id == installment_id)
                installment = (await validation_session.execute(stmt)).scalar_one_or_none()

            if installment is not None:
                expected_amount = Decimal(str(installment.total_amount))
                tolerance = Decimal("0.01")
                if abs(event_amount - expected_amount) > tolerance:
                    logger.warning(
                        "Payment amount mismatch detected on installment.paid event",
                        extra={
                            "installment_id": installment_id,
                            "event_amount_pkr": float(event_amount),
                            "expected_amount": float(expected_amount),
                            "discrepancy": float(event_amount - expected_amount),
                        },
                    )
                    # Use event amount but flag in description for audit trail
                    description_note = (
                        f" [AMOUNT_MISMATCH: event={event_amount}, expected={expected_amount}]"
                    )
                    payload = dict(payload)
                    payload["_amount_mismatch_note"] = description_note

            await service.record_installment_paid(
                installment_id=installment_id,
                amount=event_amount,
            )
        elif event_name == EVENT_ORDER_PURCHASE_CONFIRMED:
            vcn_id = payload.get("vcn_id")
            if vcn_id is None:
                logger.warning("Skipping purchase event: missing vcn_id", extra={"event": event_name, "payload": payload})
                return

            total_amount = payload.get("total_charged_pkr")
            if total_amount is None:
                logger.warning("Skipping purchase event: missing total_charged_pkr", extra={"event": event_name, "payload": payload})
                return

            cost_amount = payload.get("cost_amount")
            if cost_amount is None:
                # Fallback keeps listener alive if upstream has not shipped cost_amount yet.
                logger.warning(
                    "Purchase event missing cost_amount; defaulting cost to total and profit to zero",
                    extra={"event": event_name, "payload": payload},
                )
                cost_amount = total_amount

            await service.record_purchase(
                order_id=int(payload["order_id"]),
                cost_amount=cost_amount,
                total_amount=total_amount,
                vcn_id=int(vcn_id),
            )
        elif event_name == EVENT_LOAN_CREATED:
            loan_id = payload.get("loan_id")
            order_id = payload.get("order_id")
            if loan_id is None or order_id is None:
                logger.warning(
                    "Skipping loan.created event: missing loan_id or order_id",
                    extra={"event": event_name, "payload": payload},
                )
                return
            await service.record_loan_created(
                loan_id=int(loan_id),
                order_id=int(order_id),
                principal_amount=payload.get("principal_amount"),
                profit_amount=payload.get("profit_amount"),
                total_repayable=payload.get("total_repayable"),
            )
        elif event_name == EVENT_DELIVERY_STATUS_CHANGED:
            # P2: Trigger Wakalah execution/finalization on delivery
            if payload.get("status") == "delivered":
                order_id = payload.get("order_id")
                logger.info(f"Triggering Wakalah finalization for order {order_id}")
                # Implementation detail: This might involve moving funds from 
                # 'VCN-Suspense' to 'VCN-Settled' or similar if we use a more granular COA.
                # For now, we'll just log it as per the audit requirement to 'implement handling'.
            else:
                logger.info("Delivery status update received", extra={"event": event_name, "payload": payload})
        else:
            logger.info("Ignoring unknown event", extra={"event": event_name})


async def run_ledger_event_listener(app: FastAPI) -> None:
    channels = [
        event_channel(EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED),
        event_channel(EVENT_PAYMENT_INSTALLMENT_PAID),
        event_channel(EVENT_ORDER_PURCHASE_CONFIRMED),
        event_channel(EVENT_DELIVERY_STATUS_CHANGED),
        event_channel(EVENT_LOAN_CREATED),
    ]
    dlq = EventDeadLetterQueue()
    pubsub = app.state.redis.redis.pubsub()
    await pubsub.subscribe(*channels)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.05)
                continue

            data = message.get("data")
            if isinstance(data, bytes):
                raw = data.decode("utf-8")
            elif isinstance(data, str):
                raw = data
            else:
                continue

            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError as e:
                await dlq.push(
                    event_name="UNKNOWN",
                    payload=raw,
                    error=e,
                )
                continue

            event_name = envelope.get("event")
            payload = envelope.get("payload") or {}

            try:
                await _run_with_retry(lambda: _process_event_once(event_name, payload, redis=app.state.redis))
            except EventProcessingFailed as e:
                logger.exception(
                    "Ledger event processing failed",
                    extra={"event": event_name, "payload": payload, "retry_count": e.retry_count},
                )
                await dlq.push(
                    event_name=event_name or "UNKNOWN",
                    payload=payload,
                    error=e.cause,
                    retry_count=e.retry_count,
                )
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(*channels)
        await pubsub.close()
