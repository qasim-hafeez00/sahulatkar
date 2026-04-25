"""
Refund Service.

Orchestrates refund/reversal flows across gateways.
This service:
  - Calls the appropriate gateway client to initiate the refund
  - Records the refund transaction in PaymentTransaction
  - Publishes `payment.refund_initiated` event for Ledger Service to record reversal

BV-02/BV-03 fix: This service no longer imports Order or OrderState.
Order eligibility validation is the responsibility of the caller (API layer) before
invoking this service. The Payment Orchestrator only receives an order_id as a trusted
reference — it does not own Order state.

This service does NOT create ledger journal entries directly.
The Ledger Service subscribes to the pub/sub event and records the reversal.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.events import build_event_envelope, event_channel
from sk_shared.models.payment import PaymentTransaction
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.services.jazzcash import JazzCashClient
from src.services.raast import RaastClient
from src.services.safepay import SafepayClient

logger = logging.getLogger(__name__)

EVENT_PAYMENT_REFUND_INITIATED = "payment.refund_initiated"


class RefundService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis

    async def initiate_refund(
        self,
        *,
        order_id: int,
        user_id: int,
        amount_pkr: Decimal,
        reason: str,
        refund_reference: str,
    ) -> PaymentTransaction:
        """
        Initiate a refund for a given order.

        BV-02/BV-03 fix: No Order model import or state check performed here.
        The calling API layer (payments.py) has already validated order ownership and
        eligibility before calling this service.

        Finds the original successful payment transaction, calls the gateway,
        and records the refund transaction.
        """
        # ── 1. Find original successful transaction ───────────────────────────
        original_txn = await self.db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.user_id == user_id,
                PaymentTransaction.status == "success",
                PaymentTransaction.amount > 0,
                PaymentTransaction.installment_id.is_(None),  # Down payment, not installment
            ).order_by(PaymentTransaction.id.asc()).limit(1)
        )

        if original_txn is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="NO_SUCCESSFUL_TRANSACTION_FOUND",
            )

        # ── 2. Idempotency: check if refund already initiated ─────────────────
        idem_key = f"sk:refund:idem:{refund_reference}"
        if await self.redis.get(idem_key):
            existing_refund = await self.db.scalar(
                select(PaymentTransaction).where(
                    PaymentTransaction.gateway_response.op("->>")(
                        "refund_reference"
                    ) == refund_reference
                )
            )
            if existing_refund:
                return existing_refund

        # ── 3. Call gateway ──────────────────────────────────────────────────
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
                # JazzCash refunds require manual reconciliation for MVP.
                # Record internally — ops team processes manually via reconciliation report.
                gateway_refund_id = f"jc_refund_{order_id}_{int(datetime.now().timestamp())}"
                logger.info(
                    "JazzCash refund recorded (manual processing required)",
                    extra={"order_id": order_id, "gateway_txn_id": original_txn.gateway_txn_id},
                )
            elif gateway == "raast":
                # Raast refunds are credit transfers in reverse direction.
                # In Pakistan, this usually requires manual bank portal entry for merchants.
                gateway_refund_id = f"raast_refund_{order_id}_{int(datetime.now().timestamp())}"
                logger.info(
                    "Raast refund recorded (manual processing required)",
                    extra={"order_id": order_id, "payer_iban": original_txn.gateway_txn_id},
                )
            elif gateway == "stripe":
                # Stripe Issuing refunds: unload amount from card or cancel card.
                # For MVP: record and emit event; automated Stripe Issuing reversal logic
                # will be implemented when full Issuing API access is provisioned.
                gateway_refund_id = f"re_{order_id}_{int(datetime.now().timestamp())}"
                logger.info(
                    "Stripe Issuing refund recorded (mock)",
                    extra={"order_id": order_id, "vcn_id": original_txn.gateway_txn_id},
                )
        except Exception as exc:
            logger.error(
                "Refund gateway call failed",
                extra={"gateway": gateway, "order_id": order_id, "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"REFUND_GATEWAY_ERROR: {gateway}",
            ) from exc

        # ── 4. Record refund transaction ──────────────────────────────────────
        refund_txn = PaymentTransaction(
            loan_id=original_txn.loan_id,
            installment_id=None,
            user_id=user_id,
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

        # ── 5. Set idempotency key in Redis (24h TTL) ─────────────────────────
        await self.redis.set(idem_key, str(refund_txn.id), ttl=86400)

        # ── 6. Publish event for Ledger Service ───────────────────────────────
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
