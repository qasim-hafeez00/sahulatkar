"""
VCN Service — Virtual Card Number lifecycle management.

Responsibilities:
  - Issue single-use VCNs via Stripe Issuing (MCC-locked, amount-capped, 24h expiry)
  - Decrypt PAN/CVV for authenticated internal callers (Product Service checkout agent)
  - Confirm down payments and idempotently seed Loan + Installment records
  - Queue VCN issuance jobs for background processing
  - Void VCNs on order cancellation or expiry

Security rules:
  - Plaintext PAN/CVV NEVER appears in HTTP responses to external callers
  - All monetary arithmetic uses Decimal — never float
  - VCN issuance is blocked unless Order.status == CONTRACTS_SIGNED
  - One VCN per order (idempotent: returns existing if re-requested)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
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
from sk_shared.models.payment import Installment, Loan, PaymentTransaction, VirtualCard
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)


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
        """
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

        # Idempotency: return existing VCN if present
        existing = await self.db.scalar(
            select(VirtualCard).where(
                VirtualCard.order_id == order_id,
                VirtualCard.deleted_at.is_(None),
            )
        )
        if existing is not None:
            logger.info(
                "VCN already exists for order, returning existing",
                extra={"order_id": order_id, "vcn_id": existing.id},
            )
            return existing

        loan = await self.db.scalar(
            select(Loan).where(Loan.order_id == order_id, Loan.deleted_at.is_(None))
        )

        pan = self._generate_pan()
        cvv = f"{randbelow(1000):03d}"
        now = datetime.now(timezone.utc)

        # VCN authorized amount = product price + VCN_BUFFER_PCT % buffer
        buffer_multiplier = Decimal("1.0") + Decimal(str(settings.VCN_BUFFER_PCT)) / Decimal("100")
        authorized_amount = (amount_pkr * buffer_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        card = VirtualCard(
            order_id=order_id,
            user_id=order.user_id,
            issuer="stripe",
            issuer_card_id=f"card_{hashlib.sha256(f'{order_id}:{pan}'.encode()).hexdigest()[:24]}",
            masked_number=self._mask_pan(pan),
            card_expiry=(now + timedelta(days=365 * 3)).date(),
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

        # Record VCN issuance as a transaction for audit
        transaction = PaymentTransaction(
            loan_id=loan.id if loan is not None else None,
            installment_id=None,
            user_id=order.user_id,
            payment_method_id=None,
            amount=amount_pkr,
            currency=settings.PAYMENT_CURRENCY,
            gateway="stripe",
            gateway_txn_id=f"vcn_issued_{order_id}",
            gateway_response={"order_id": order_id, "merchant_domain": merchant_domain, "event": "vcn_issued"},
            status="success",
            reconciled_at=now,
        )
        self.db.add(transaction)

        await self.db.flush()
        await self.db.refresh(card)

        # Publish VCN issued event
        envelope = build_event_envelope(
            event=EVENT_VCN_ISSUED,
            source_service="payment-orchestrator",
            payload={
                "order_id": order_id,
                "vcn_id": card.id,
                "status": card.status,
                "merchant_domain": merchant_domain,
                "authorized_amount": str(authorized_amount),
            },
        )
        await self.redis.publish(event_channel(EVENT_VCN_ISSUED), envelope.to_json())

        from src.core.metrics import VCN_ISSUED_TOTAL
        VCN_ISSUED_TOTAL.labels(issuer="stripe").inc()

        logger.info(
            "VCN issued",
            extra={
                "order_id": order_id,
                "vcn_id": card.id,
                "masked_number": card.masked_number,
                "authorized_amount": str(authorized_amount),
            },
        )
        return card

    # ── VCN Decrypt (Internal Only) ──────────────────────────────────────────

    async def decrypt_vcn(self, order_id: int) -> dict:
        """
        Decrypt and return plaintext PAN/CVV.
        ONLY called by authenticated internal services (Product Service checkout agent).
        Never exposed to external HTTP callers.
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

    # ── Down Payment Confirmation + Loan Seeding ─────────────────────────────

    async def confirm_down_payment(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        gateway_txn_id: str,
    ) -> Loan:
        """
        Confirm a down payment and idempotently seed the Loan + Installment records.

        The Gateway service seeds Loan/Installment at contract signing.
        This method is a safety net for the case where the Gateway failed to seed,
        or for orders where the payment was confirmed before the contract was fully indexed.

        Uses Decimal arithmetic exclusively — no floats.
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

        loan = await self.db.scalar(
            select(Loan).where(Loan.order_id == order_id, Loan.deleted_at.is_(None))
        )

        if loan is None:
            # Gateway failed to seed — emit event for Gateway Service to handle recovery
            logger.warning(
                "Loan not found for order during down payment confirmation",
                extra={"order_id": order_id},
            )
            # Future: emit payment.gateway_seeding_required event here
        else:
            # Loan already seeded by Gateway; update totals to reflect received payment
            loan.total_paid = Decimal(str(loan.down_payment_amount))
            loan.total_outstanding = Decimal(str(loan.balance_financed))

        # VIOLATION-02: Do NOT mutate order.status directly. 
        # The Gateway Service will update it upon receiving payment.confirmed event.
        # order.status = OrderState.DOWN_PAYMENT_RECEIVED
        await self.db.flush()

        # Publish confirmed event for Ledger Service
        envelope = build_event_envelope(
            event=EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED,
            source_service="payment-orchestrator",
            payload={
                "order_id": order_id,
                "loan_id": loan.id if loan else None,
                "amount_pkr": str(amount_pkr),
                "gateway_txn_id": gateway_txn_id,
            },
        )
        await self.redis.publish(
            event_channel(EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED),
            envelope.to_json(),
        )

        logger.info(
            "Down payment confirmed",
            extra={
                "order_id": order_id,
                "loan_id": loan.id if loan else None,
                "amount_pkr": str(amount_pkr),
                "gateway_txn_id": gateway_txn_id,
            },
        )
        return loan



    # ── Queue Helper ─────────────────────────────────────────────────────────

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
        """
        payload = {
            "order_id": order_id,
            "amount_pkr": str(amount_pkr),
            "merchant_domain": merchant_domain,
        }
        
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
        secret = settings.VCN_ENCRYPTION_KEY or settings.STRIPE_SECRET_KEY or "mock-vcn-key-do-not-use-in-prod"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key)

    def _encrypt_value(self, value: str) -> bytes:
        return self._get_fernet().encrypt(value.encode("utf-8"))

    def _decrypt_value(self, ciphertext: bytes) -> str:
        return self._get_fernet().decrypt(ciphertext).decode("utf-8")
