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
  - PAN/CVV are encrypted with a versioned key envelope (VcnKeyProvider in
    src/services/vcn_encryption.py) — the key version used is stamped on the
    VirtualCard row (encryption_key_version) so old ciphertext keeps
    decrypting correctly after the current key version is rotated.

Boundary rules (DDD):
  - BV-01: Do NOT mutate Loan.total_paid / Loan.total_outstanding here.
           Emit payment.down_payment_confirmed event via outbox. Let Gateway/Ledger update Loan.
  - INR-04: Do NOT create PaymentTransaction records for VCN issuance.
            VCN issuance is not a payment transaction. Use structured logging + outbox event.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from secrets import randbelow
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.events import (
    EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED,
    EVENT_VCN_ISSUED,
    build_event_envelope,
)
from sk_shared.models.contracts import MurabahaContract
from sk_shared.models.order import Order
from sk_shared.models.payment import PaymentTransaction, VirtualCard
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.models.outbox import OutboxEvent
from src.services.vcn_encryption import VcnKeyProvider

logger = logging.getLogger(__name__)


class VcnService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis
        # Instance-scoped (not module-global) so that rotating
        # VCN_ENCRYPTION_KEY_CURRENT_VERSION takes effect on the very next
        # VcnService construction (a fresh instance is built per request —
        # see src/api/v1/vcn.py) instead of being pinned forever by a
        # process-lifetime cache, which is what made the old single static
        # key un-rotatable without a process restart.
        self._key_provider = VcnKeyProvider(db)

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
            # Live-verified bug: queue_issue()'s caller is always
            # confirm_down_payment's sequel (payments.py's own /down-payment
            # endpoint, payment_webhook_consumer.py, payment_initiate_consumer.py),
            # and by the time the queued vcn.issue job actually runs, Gateway's
            # /internal/payments/{id}/confirm callback has already advanced
            # Order.status from CONTRACTS_SIGNED to DOWN_PAYMENT_RECEIVED —
            # exactly per the intended contracts-signed -> down-payment ->
            # VCN-issuance flow. Requiring CONTRACTS_SIGNED here meant every
            # real (non-test) VCN issuance was rejected the moment the
            # gateway.payment_confirmed notification (GAP fixed this session)
            # actually started working. CONTRACTS_SIGNED is still accepted so
            # existing direct-call tests/callers that never advance Order.status
            # keep working — mirrors confirm_down_payment's own multi-state gate.
            if order.status not in {OrderState.CONTRACTS_SIGNED, OrderState.DOWN_PAYMENT_RECEIVED}:
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

            # Resolve MCC (simplified for this context)
            mcc = "5999"

            # Issuer selection: Lithic is code-complete (real merchant-domain
            # locking via authorization rules, unlike Stripe's MCC-only lock)
            # but gated off by default — it requires a business/KYB approval
            # process before it can issue a single real card. Stripe Issuing
            # remains the functional-today path until that approval lands.
            if settings.FEATURE_LITHIC_ENABLED:
                from src.adapters.lithic import LithicAdapter
                issuer_adapter = LithicAdapter(
                    api_key=settings.LITHIC_API_KEY,
                    base_url=settings.LITHIC_BASE_URL,
                    card_program_token=settings.LITHIC_CARD_PROGRAM_TOKEN,
                    fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                    fx_buffer_pct=settings.FX_BUFFER_PCT,
                )
                issuer_name = "lithic"
                amount_usd_cents = issuer_adapter._pkr_to_usd_cents(authorized_amount)
                issued_card = issuer_adapter.create_card(
                    cardholder_id=stripe_cardholder_id,
                    authorized_amount_cents=amount_usd_cents,
                    merchant_category=mcc,
                    merchant_domain=merchant_domain,
                )
            else:
                from src.adapters.stripe_issuing import StripeIssuingAdapter
                issuer_adapter = StripeIssuingAdapter(
                    secret_key=settings.STRIPE_SECRET_KEY,
                    fx_pkr_to_usd=settings.FX_PKR_TO_USD_RATE,
                    fx_buffer_pct=settings.FX_BUFFER_PCT,
                )
                issuer_name = "stripe"
                amount_usd_cents = issuer_adapter._pkr_to_usd_cents(authorized_amount)
                issued_card = issuer_adapter.create_card(
                    cardholder_id=stripe_cardholder_id,
                    authorized_amount_cents=amount_usd_cents,
                    merchant_category=mcc,
                )

            pan = issued_card["pan"]
            cvv = issued_card["cvv"]

            # Both fields are encrypted under the same (current) key version —
            # only one version tag needs to be stored per row.
            encrypted_pan, key_version = await self._encrypt_value(pan)
            encrypted_cvv, _ = await self._encrypt_value(cvv)

            card = VirtualCard(
                order_id=order_id,
                user_id=order.user_id,
                issuer=issuer_name,
                issuer_card_id=issued_card["issuer_card_id"],
                stripe_cardholder_id=stripe_cardholder_id,
                masked_number=self._mask_pan(pan),
                card_expiry=datetime(int(issued_card["expiry_year"]), int(issued_card["expiry_month"]), 1).date(),
                authorized_amount=authorized_amount,
                loaded_amount=amount_pkr,
                mcc_lock="retail",
                merchant_lock=merchant_domain,
                charged_amount=Decimal("0.00"),
                is_used=False,
                status="active",
                issued_at=now,
                expires_at=now + timedelta(hours=settings.VCN_EXPIRY_HOURS),
                encrypted_pan=encrypted_pan,
                encrypted_cvv=encrypted_cvv,
                encryption_key_version=key_version,
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
            VCN_ISSUED_TOTAL.labels(issuer=issuer_name).inc()

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

        # Decrypt using whichever key version was stamped on this row at
        # issuance time — not necessarily the current version, so old VCNs
        # keep decrypting correctly across key rotations.
        pan = await self._decrypt_value(card.encrypted_pan, card.encryption_key_version)
        cvv = await self._decrypt_value(card.encrypted_cvv, card.encryption_key_version)

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

        # P0-01 fix: the event above reaches Ledger (which posts the GL entry)
        # but nothing was calling Gateway's own
        # POST /internal/payments/{payment_id}/confirm — the only code path
        # that advances Order.status past CONTRACTS_SIGNED and runs Gateway's
        # saga-compensation logic. A real down payment therefore never moved
        # the order forward in production; only a dev-simulated endpoint did.
        # Look up the Gateway-created PaymentTransaction for this down payment
        # (shared table) and queue a control event that OutboxPublisher turns
        # into an HTTP call to Gateway, benefiting from the same
        # retry/backoff the rest of the outbox already has.
        txn = await self.db.scalar(
            select(PaymentTransaction)
            .where(
                PaymentTransaction.order_id == order_id,
                PaymentTransaction.transaction_type == "down_payment",
                PaymentTransaction.status.in_(["initiated", "pending"]),
                PaymentTransaction.deleted_at.is_(None),
            )
            .order_by(PaymentTransaction.created_at.desc())
        )
        if txn is not None:
            await self._queue_outbox_event(
                "gateway.payment_confirmed",
                {
                    "payment_id": txn.id,
                    "gateway_txn_id": gateway_txn_id,
                    "status": "confirmed",
                },
            )
        else:
            logger.warning(
                "No matching Gateway PaymentTransaction found for down payment "
                "confirmation — Order status will not advance past CONTRACTS_SIGNED",
                extra={"order_id": order_id},
            )

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

    async def _encrypt_value(self, value: str) -> tuple[bytes, str]:
        """Encrypt with the current VCN key version. Returns (ciphertext, version_tag).

        See src/services/vcn_encryption.py::VcnKeyProvider for the versioned
        envelope scheme (local-mock vs. production-KMS split, rotation).
        """
        return await self._key_provider.encrypt(value)

    async def _decrypt_value(self, ciphertext: bytes, key_version: Optional[str]) -> str:
        """Decrypt using the key version stamped on the record.

        `key_version` should be `VirtualCard.encryption_key_version`, which may
        be None for rows written before that column existed (treated as the
        legacy "v1" version — see VcnKeyProvider.LEGACY_VERSION).
        """
        return await self._key_provider.decrypt(ciphertext, key_version)
