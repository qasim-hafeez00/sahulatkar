from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import FastAPI

from sk_shared.events import EVENT_DELIVERY_STATUS_CHANGED, EVENT_ORDER_PURCHASE_CONFIRMED, EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED, event_channel

from src.core.database import SessionLocal
from src.core.event_dlq import EventDeadLetterQueue
from src.services.accounting_service import AccountingService


logger = logging.getLogger(__name__)


async def run_ledger_event_listener(app: FastAPI) -> None:
    channels = [
        event_channel(EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED),
        event_channel(EVENT_ORDER_PURCHASE_CONFIRMED),
        event_channel(EVENT_DELIVERY_STATUS_CHANGED),
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
                async with SessionLocal() as session:
                    service = AccountingService(session)
                    if event_name == EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED:
                        await service.record_down_payment(order_id=int(payload["order_id"]), amount=payload["amount_pkr"])
                    elif event_name == EVENT_ORDER_PURCHASE_CONFIRMED:
                        vcn_id = payload.get("vcn_id")
                        if vcn_id is None:
                            logger.warning("Skipping purchase event: missing vcn_id", extra={"event": event_name, "payload": payload})
                            continue

                        total_amount = payload.get("total_charged_pkr")
                        if total_amount is None:
                            logger.warning("Skipping purchase event: missing total_charged_pkr", extra={"event": event_name, "payload": payload})
                            continue

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
                    elif event_name == EVENT_DELIVERY_STATUS_CHANGED:
                        logger.info("Delivery status event received", extra={"event": event_name, "payload": payload})
                    else:
                        logger.info("Ignoring unknown event", extra={"event": event_name})
            except Exception as e:
                logger.exception("Ledger event processing failed", extra={"event": event_name, "payload": payload})
                await dlq.push(
                    event_name=event_name or "UNKNOWN",
                    payload=payload,
                    error=e,
                )
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(*channels)
        await pubsub.close()
