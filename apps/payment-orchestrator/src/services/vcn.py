"""
VCN Service — Virtual Card Number lifecycle management.

Responsibilities:
  - Issue single-use VCNs via Stripe Issuing (MCC-locked, amount-capped, 24h expiry)
  - Decrypt PAN/CVV for authenticated internal callers (Product Service checkout agent)
  - Confirm down payments and emit events (does NOT mutate Loan/Order — BV-01 fix)
  - Queue VCN issuance jobs for background processing
  - Void VCNs on order cancellation or expiry

Security rules:
  - Plaintext PAN/CVV NEVER appears in HTTP responses to external callers
  - All monetary arithmetic uses Decimal — never float
  - VCN issuance is blocked unless Order.status == CONTRACTS_SIGNED
  - One VCN per order (idempotent: returns existing if re-requested)

Boundary rules (DDD):
  - BV-01: Do NOT mutate Loan.total_paid / Loan.total_outstanding here.
           Emit payment.down_payment_confirmed event via outbox. Let Gateway/Ledger update Loan.
  - INR-04: Do NOT create PaymentTransaction records for VCN issuance.
            VCN issuance is not a payment transaction. Use structured logging + outbox event.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from secrets import randbelow
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, QueueName
from sk_shared.events import (
    EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED,
    EVENT_VCN_ISSUED,
    build_event_envelope,
    event_channel,
)
from sk_shared.models.contracts import MurabahaContract
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)
_fernet_instance: Fernet | None = None


class VcnService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis

    # ── VCN Issuance ────────────────────────────────────────────────────────

    async def issue_vcn(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        merchant_domain: str | None = None,
    ) -> VirtualCard:
        """
        Issue a single-use, MCC-locked VCN for the checkout agent.

        Hard gate: Order MUST be in CONTRACTS_SIGNED state with a signed
        MurabahaContract before a VCN can be issued.

        Idempotent: returns existing active VCN if one already exists for the order.

        INR-04 fix: No PaymentTransaction record is created. VCN issuance is not a
        payment transaction. Structured log + vcn.issued event via outbox.
        """
        import time
        start = time.perf_counter()
        try:
            order = await self._get_order(order_id)
            if order.status != OrderState.CONTRACTS_SIGNED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="MURABAHA_NOT_SIGNED",
                )

            contract = await self._get_signed_contract(order_id)
            if contract is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="MURABAHA_NOT_SIGNED",
                )

            # Price drift check (NEW)
            stored_total = Decimal(str(order.total_amount))
            drift = abs(amount_pkr - stored_total) / stored_total if stored_total > 0 else Decimal("1")
            if drift > Decimal("0.05"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"PRICE_DRIFT_EXCEEDED: requested {amount_pkr}, stored {stored_total}",
                )

            # Idempotency: return existing VCN if present
            existing = await self.db.scalar(
                select(VirtualCard).where(
                    VirtualCard.order_id == order_id,
                    VirtualCard.deleted_at.is_(None),
                )
            )
            if existing is not None:
                logger.info(
                    "VCN already exists for order — returning existing",
                    extra={"order_id": order_id, "vcn_id": existing.id},
                )
                return existing

            now = datetime.now(timezone.utc)

            # VCN authorized amount = product price + VCN_BUFFER_PCT % buffer + FX buffer
            buffer_multiplier = Decimal("1.0") + Decimal(str(settings.VCN_BUFFER_PCT)) / Decimal("100") + Decimal(str(settings.FX_BUFFER_PCT)) / Decimal("100")
            authorized_amount = (amount_pkr * buffer_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
            # Calculate USD limit for Stripe
            fx_rate = Decimal(str(settings.FX_PKR_TO_USD_RATE))
            authorized_amount_usd = (authorized_amount * fx_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Stripe Cardholder
            from src.services.stripe_cardholder import StripeCardholderService
            cardholder_svc = StripeCardholderService(self.redis)
            stripe_cardholder_id = await cardholder_svc.get_or_create(user_id=order.user_id)
        
            # Real Stripe card creation
            from src.adapters.stripe_issuing import StripeIssuingAdapter
            stripe_adapter = StripeIssuingAdapter(
                secret_key=settings.STRIPE_SECRET_KEY,
                fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                fx_buffer_pct=settings.FX_BUFFER_PCT,
            )
            amount_usd_cents = stripe_adapter._pkr_to_usd_cents(authorized_amount)
        
            # Resolve MCC (simplified for this context)
            mcc = "5999"
        
            stripe_card = stripe_adapter.create_card(
                cardholder_id=stripe_cardholder_id,
                authorized_amount_cents=amount_usd_cents,
                merchant_category=mcc,
            )
        
            pan = stripe_card["pan"]
            cvv = stripe_card["cvv"]

            card = VirtualCard(
                order_id=order_id,
                user_id=order.user_id,
                issuer="stripe",
                issuer_card_id=stripe_card["issuer_card_id"],
                stripe_cardholder_id=stripe_cardholder_id,
                masked_number=self._mask_pan(pan),
                card_expiry=datetime(int(stripe_card["expiry_year"]), int(stripe_card["expiry_month"]), 1).date(),
                authorized_amount=authorized_amount,
                loaded_amount=amount_pkr,
                mcc_lock="retail",
                merchant_lock=merchant_domain,
                charged_amount=Decimal("0.00"),
                is_used=False,
                status="active",
                issued_at=now,
                expires_at=now + timedelta(hours=settings.VCN_EXPIRY_HOURS),
                encrypted_pan=self._encrypt_value(pan),
                encrypted_cvv=self._encrypt_value(cvv),
            )
            self.db.add(card)

            await self.db.flush()
            await self.db.refresh(card)

            # Publish VCN issued event via transactional outbox
            envelope = build_event_envelope(
                event=EVENT_VCN_ISSUED,
                source_service="payment-orchestrator",
                payload={
                    "order_id": order_id,
                    "vcn_id": card.id,
                    "status": card.status,
                    "merchant_domain": merchant_domain,
                    "authorized_amount": str(authorized_amount),
                    "authorized_amount_usd": str(authorized_amount_usd),
                },
            )
            await self._queue_outbox_event(EVENT_VCN_ISSUED, asdict(envelope))

            from src.core.metrics import VCN_ISSUED_TOTAL
            VCN_ISSUED_TOTAL.labels(issuer="stripe").inc()

            logger.info(
                "VCN issued",
                extra={
                    "order_id": order_id,
                    "vcn_id": card.id,
                    "masked_number": card.masked_number,
                    "authorized_amount": str(authorized_amount),
                    "authorized_amount_usd": str(authorized_amount_usd),
                },
            )
            return card
        finally:
            from src.core.metrics import VCN_ISSUE_LATENCY
            VCN_ISSUE_LATENCY.observe(time.perf_counter() - start)

    # ── VCN Decrypt (Internal Only) ──────────────────────────────────────────

    async def decrypt_vcn(self, order_id: int) -> dict:
        """
        Decrypt and return plaintext PAN/CVV.
        ONLY called by authenticated internal services (Product Service checkout agent).
        Never exposed to external HTTP callers.
        Plaintext PAN/CVV must NEVER appear in log output (security rule).
        """
        card = await self.db.scalar(
            select(VirtualCard).where(
                VirtualCard.order_id == order_id,
                VirtualCard.deleted_at.is_(None),
            )
        )
        if card is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="VCN_NOT_FOUND")

        if card.status != "active":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"VCN_NOT_ACTIVE: status is {card.status}",
            )

        expires_at = card.expires_at.replace(tzinfo=timezone.utc) if card.expires_at.tzinfo is None else card.expires_at
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="VCN_EXPIRED",
            )

        pan = self._decrypt_value(card.encrypted_pan)
        cvv = self._decrypt_value(card.encrypted_cvv)

        # Security: log at DEBUG only — never INFO, never include PAN/CVV in log record
        logger.debug("VCN decrypted for checkout agent", extra={"order_id": order_id, "vcn_id": card.id})

        return {
            "vcn_id": card.id,
            "order_id": order_id,
            "pan": pan,
            "expiry_month": f"{card.card_expiry.month:02d}",
            "expiry_year": str(card.card_expiry.year),
            "cvv": cvv,
            "cardholder_name": "SahulatKar Agent",
            "expires_at": card.expires_at,
        }

    # ── Down Payment Confirmation ─────────────────────────────────────────────

    async def confirm_down_payment(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        gateway_txn_id: str,
    ) -> None:
        """
        Confirm a down payment by emitting the payment.down_payment_confirmed event.

        BV-01 fix: This method does NOT mutate Loan.total_paid or Loan.total_outstanding.
        Those fields are accounting concerns owned by the Ledger Service. The Gateway Service
        updates Loan financial totals reactively upon receiving the payment.confirmed event.

        All events flow through the outbox for transactional integrity.
        """
        order = await self._get_order(order_id)
        if order.status not in {
            OrderState.CONTRACTS_SIGNED,
            OrderState.DOWN_PAYMENT_PENDING,
            OrderState.DOWN_PAYMENT_RECEIVED,
        }:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ORDER_NOT_READY_FOR_PAYMENT",
            )

        contract = await self._get_signed_contract(order_id)
        if contract is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MURABAHA_NOT_SIGNED",
            )

        # Publish confirmed event via transactional outbox
        envelope = build_event_envelope(
            event=EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED,
            source_service="payment-orchestrator",
            payload={
                "order_id": order_id,
                "loan_id": None,  # Gateway Service looks up its own Loan by order_id
                "amount_pkr": str(amount_pkr),
                "gateway_txn_id": gateway_txn_id,
            },
        )
        await self._queue_outbox_event(EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED, asdict(envelope))

        logger.info(
            "Down payment confirmed — outbox event queued",
            extra={
                "order_id": order_id,
                "amount_pkr": str(amount_pkr),
                "gateway_txn_id": gateway_txn_id,
            },
        )

    # ── Outbox Helper ────────────────────────────────────────────────────────

    async def _queue_outbox_event(self, event_name: str, payload: dict) -> None:
        event = OutboxEvent(
            event_name=event_name,
            payload=payload,
            status="pending"
        )
        self.db.add(event)
        await self.db.flush()

    async def queue_issue(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        merchant_domain: str | None = None,
    ) -> None:
        """
        Push a VCN issue job to the Outbox for background processing.
        Ensures 100% consistency: VCN is ONLY issued if the down payment DB transaction commits.
        The OutboxPublisher worker bridges this to the VCN_ISSUE Redis queue.
        """
        payload = {
            "order_id": order_id,
            "amount_pkr": str(amount_pkr),
            "merchant_domain": merchant_domain,
        }

        # vcn.issue is a special internal outbox event handled by the publisher
        event = OutboxEvent(
            event_name="vcn.issue",
            payload=payload,
            status="pending"
        )
        self.db.add(event)
        await self.db.flush()
        logger.info("VCN issue job queued in outbox", extra={"order_id": order_id})

    # ── Private Helpers ─────────────────────────────────────────────────────

    async def _get_order(self, order_id: int) -> Order:
        order = await self.db.scalar(
            select(Order).where(Order.id == order_id, Order.deleted_at.is_(None))
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
        return order

    async def _get_signed_contract(self, order_id: int) -> Optional[MurabahaContract]:
        return await self.db.scalar(
            select(MurabahaContract).where(
                MurabahaContract.order_id == order_id,
                MurabahaContract.signed_at.is_not(None),
            )
        )

    def _generate_pan(self) -> str:
        """Generate a 16-digit PAN (BIN prefix 4 = Visa-like, for internal use)."""
        parts = [str(randbelow(10000)).zfill(4) for _ in range(4)]
        parts[0] = "4" + parts[0][1:]  # Starts with 4 (Visa BIN range)
        return "".join(parts)

    def _mask_pan(self, pan: str) -> str:
        return f"**** **** **** {pan[-4:]}"

    def _get_fernet(self) -> Fernet:
        global _fernet_instance
        if _fernet_instance is not None:
            return _fernet_instance

        secret = settings.VCN_ENCRYPTION_KEY
        if not secret:
            if settings.ENVIRONMENT == "local":
                secret = "local-dev-vcn-key"
            else:
                raise RuntimeError("VCN_ENCRYPTION_KEY is required outside local environment")

        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        _fernet_instance = Fernet(key)
        return _fernet_instance

    def _encrypt_value(self, value: str) -> bytes:
        return self._get_fernet().encrypt(value.encode("utf-8"))

    def _decrypt_value(self, ciphertext: bytes) -> str:
        return self._get_fernet().decrypt(ciphertext).decode("utf-8")
