import json
import logging
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.payment import VirtualCard
from src.core.database import SessionLocal

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
            card.status = "voided"
            card.void_reason = "order_cancelled"
            logger.info(f"VCN {card.id} voided due to order cancellation", extra={"order_id": order_id})
            await db.commit()
            
            # Future: Notify issuer (Stripe) to cancel card
        else:
            logger.debug(f"No active VCN found for cancelled order {order_id}")


async def start_listeners(redis):
    """
    Subscribe to Redis events and dispatch to handlers.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe("sk:events:order.cancelled")
    
    logger.info("Started listening for events")
    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = json.loads(message["data"])
                event_name = data.get("event")
                payload = data.get("payload", {})
                
                if event_name == "order.cancelled":
                    await handle_order_cancelled(payload)
            except Exception as e:
                logger.error(f"Error processing event: {e}")
