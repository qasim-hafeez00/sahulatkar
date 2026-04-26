import json
import logging
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.payment import VirtualCard
from src.core.database import SessionLocal
from src.core.metrics import EVENT_LISTENER_UP

logger = logging.getLogger(__name__)


async def handle_order_cancelled(payload: Dict[str, Any]):
    """
    Listener for order.cancelled event.
    Voids the VCN associated with the order.
    """
    order_id = payload.get("order_id")
    if not order_id:
        return

    async with SessionLocal() as db:
        card = await db.scalar(
            select(VirtualCard).where(
                VirtualCard.order_id == order_id,
                VirtualCard.status == "active"
            )
        )
        if card:
            from src.adapters.stripe_issuing import StripeIssuingAdapter
            from src.config import settings

            stripe_adapter = StripeIssuingAdapter(
                secret_key=settings.STRIPE_SECRET_KEY,
                fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                fx_buffer_pct=settings.FX_BUFFER_PCT,
            )
            stripe_cancel_ok = stripe_adapter.cancel_card(card.issuer_card_id)
            if not stripe_cancel_ok:
                logger.error(
                    "Stripe cancellation failed during order.cancelled handling",
                    extra={"order_id": order_id, "vcn_id": card.id, "issuer_card_id": card.issuer_card_id},
                )

            card.status = "voided"
            card.void_reason = "order_cancelled"
            logger.info(
                f"VCN {card.id} voided due to order cancellation",
                extra={"order_id": order_id, "stripe_canceled": stripe_cancel_ok},
            )
            await db.commit()
        else:
            logger.debug(f"No active VCN found for cancelled order {order_id}")


async def start_listeners(redis):
    """Supervised Redis pub/sub listener with exponential backoff reconnect."""
    import asyncio
    backoff = 1
    while True:
        pubsub = None
        try:
            EVENT_LISTENER_UP.set(0)
            pubsub = redis.pubsub()
            await pubsub.subscribe(
                "sk:events:order.cancelled",
                "sk:events:vcn.issue_requested",
            )
            logger.info("Event listener connected to Redis pub/sub")
            EVENT_LISTENER_UP.set(1)
            backoff = 1  # Reset on successful connection
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    event_name = data.get("event")
                    payload = data.get("payload", {})
                    if event_name == "order.cancelled":
                        await handle_order_cancelled(payload)
                    # Add future handlers here
                except Exception as e:
                    event_name = data.get("event", "unknown") if 'data' in locals() else "unknown"
                    logger.error(f"Error processing event {event_name}: {e}",
                                 extra={"event": event_name})
        except Exception as e:
            EVENT_LISTENER_UP.set(0)
            logger.error(f"Event listener disconnected: {e}. Reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # Exponential backoff, cap at 60s
        finally:
            if pubsub is not None:
                try:
                    await pubsub.close()
                except Exception:
                    pass
