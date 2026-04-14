from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import FastAPI

from sk_shared.events import EVENT_DELIVERY_STATUS_CHANGED, EVENT_ORDER_PURCHASE_CONFIRMED, EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED, event_channel

from src.core.database import SessionLocal
from src.services.accounting_service import AccountingService


async def run_ledger_event_listener(app: FastAPI) -> None:
    channels = [
        event_channel(EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED),
        event_channel(EVENT_ORDER_PURCHASE_CONFIRMED),
        event_channel(EVENT_DELIVERY_STATUS_CHANGED),
    ]
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
            except json.JSONDecodeError:
                continue

            event_name = envelope.get("event")
            payload = envelope.get("payload") or {}

            async with SessionLocal() as session:
                service = AccountingService(session)
                if event_name == EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED:
                    await service.record_down_payment(order_id=int(payload["order_id"]), amount=payload["amount_pkr"])
                elif event_name == EVENT_ORDER_PURCHASE_CONFIRMED:
                    vcn_id = payload.get("vcn_id")
                    if vcn_id is not None:
                        await service.record_purchase(order_id=int(payload["order_id"]), amount=payload["total_charged_pkr"], vcn_id=int(vcn_id))
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(*channels)
        await pubsub.close()
