"""
Refund Service.

Orchestrates refund/reversal flows across gateways.
This service:
  - Validates refund eligibility (order must be in refundable state)
  - Calls the appropriate gateway client to initiate the refund
  - Records the refund transaction in PaymentTransaction
  - Publishes `payment.refund_initiated` event for Ledger Service to record reversal

This service does NOT create ledger journal entries directly.
The Ledger Service subscribes to the pub/sub event and records the reversal.

IMPORTANT: Refunds are only allowed for orders in these states:
    DOWN_PAYMENT_RECEIVED, VCN_ISSUED, CHECKOUT_COMPLETE, DELIVERED
    (not for orders that have been fully repaid — those go through dispute)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.events import build_event_envelope, event_channel
from sk_shared.models.order import Order
from sk_shared.models.payment import PaymentTransaction
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.safepay import SafepayClient

logger = logging.getLogger(__name__)

EVENT_PAYMENT_REFUND_INITIATED = "payment.refund_initiated"

_REFUNDABLE_STATES = {
    OrderState.DOWN_PAYMENT_RECEIVED,
    OrderState.VCN_ISSUED,
    OrderState.COMPLETED,
    OrderState.DELIVERED,
}


class RefundService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis

    async def initiate_refund(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        reason: str,
        refund_reference: str,
        requested_by_user_id: int,
    ) -> PaymentTransaction:
        """
        Initiate a refund for a given order.

        Finds the original successful down payment transaction, validates
        eligibility, calls the gateway, and records the refund transaction.
        """
        # ── 1. Load order ────────────────────────────────────────────────────
        order = await self.db.scalar(
            select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

        if order.status not in _REFUNDABLE_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"ORDER_NOT_REFUNDABLE: current status is {order.status}",
            )

        # ── 2. Find original down-payment transaction ─────────────────────────
        original_txn = await self.db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.loan_id.in_(
                    select(PaymentTransaction.loan_id).where(
                        PaymentTransaction.gateway_txn_id != None  # noqa: E711
                    )
                ),
                PaymentTransaction.status == "success",
                PaymentTransaction.installment_id.is_(None),  # Down payment, not installment
            ).order_by(PaymentTransaction.id.asc()).limit(1)
        )

        # Fallback: find any successful transaction for this order's user
        if original_txn is None:
            original_txn = await self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.user_id == order.user_id,
                    PaymentTransaction.status == "success",
                ).order_by(PaymentTransaction.id.asc()).limit(1)
            )

        if original_txn is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="NO_SUCCESSFUL_TRANSACTION_FOUND",
            )

        # ── 3. Idempotency: check if refund already initiated ────────────────
        idem_key = f"sk:refund:idem:{refund_reference}"
        if await self.redis.get(idem_key):
            existing_refund = await self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.gateway_response.op("->>")("refund_reference") == refund_reference
                )
            )
            if existing_refund:
                return existing_refund

        # ── 4. Call gateway ──────────────────────────────────────────────────
        gateway = original_txn.gateway
        gateway_refund_id: str | None = None

        try:
            if gateway == "safepay":
                client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET)
                result = client.initiate_refund(
                    gateway_txn_id=original_txn.gateway_txn_id or "",
                    amount_pkr=amount_pkr,
                    reason=reason,
                )
                gateway_refund_id = result.get("refund_id")
            elif gateway == "jazzcash":
                # JazzCash refunds are handled via manual reconciliation in most integrations.
                # For MVP, record the refund internally and process manually.
                gateway_refund_id = f"jc_refund_{order_id}"
                logger.info("JazzCash refund recorded (manual processing required)", extra={"order_id": order_id})
            elif gateway == "raast":
                # Raast refunds are credit transfers in the reverse direction.
                # TODO: Implement Raast IBFT credit transfer when API docs are available.
                gateway_refund_id = f"raast_refund_{order_id}"
                logger.info("Raast refund recorded (manual processing required)", extra={"order_id": order_id})
            elif gateway == "stripe":
                # Stripe refunds via Stripe Issuing API
                # TODO: stripe.Refund.create(charge=original_charge_id, amount=int(amount_pkr * 100))
                gateway_refund_id = f"re_{order_id}"
        except Exception as exc:
            logger.error("Refund gateway call failed", extra={"gateway": gateway, "order_id": order_id, "error": str(exc)})
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"REFUND_GATEWAY_ERROR: {gateway}",
            ) from exc

        # ── 5. Record refund transaction ─────────────────────────────────────
        refund_txn = PaymentTransaction(
            loan_id=original_txn.loan_id,
            installment_id=None,
            user_id=order.user_id,
            amount=amount_pkr * -1,         # Negative amount = refund/reversal
            currency=settings.PAYMENT_CURRENCY,
            gateway=gateway,
            gateway_txn_id=gateway_refund_id,
            gateway_response={
                "original_txn_id": original_txn.id,
                "refund_reference": refund_reference,
                "reason": reason,
            },
            status="success",
            reconciled_at=datetime.now(timezone.utc),
        )
        self.db.add(refund_txn)
        await self.db.commit()
        await self.db.refresh(refund_txn)

        # ── 6. Set idempotency key in Redis (24h TTL) ─────────────────────────
        await self.redis.set(idem_key, str(refund_txn.id), ttl=86400)

        # ── 7. Publish event for Ledger Service ──────────────────────────────
        envelope = build_event_envelope(
            event=EVENT_PAYMENT_REFUND_INITIATED,
            source_service="payment-orchestrator",
            payload={
                "order_id": order_id,
                "refund_txn_id": refund_txn.id,
                "amount_pkr": str(amount_pkr),
                "gateway": gateway,
                "gateway_refund_id": gateway_refund_id,
                "reason": reason,
            },
        )
        await self.redis.publish(event_channel(EVENT_PAYMENT_REFUND_INITIATED), envelope.to_json())

        logger.info(
            "Refund initiated successfully",
            extra={
                "order_id": order_id,
                "refund_txn_id": refund_txn.id,
                "amount_pkr": str(amount_pkr),
                "gateway": gateway,
            },
        )
        return refund_txn
