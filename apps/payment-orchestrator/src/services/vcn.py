from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from secrets import randbelow
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName, OrderState
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


class VcnService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis

    async def issue_vcn(
        self,
        *,
        order_id: int,
        amount_pkr: float,
        merchant_domain: str | None = None,
    ) -> VirtualCard:
        order = await self._get_order(order_id)
        if order.status != OrderState.CONTRACTS_SIGNED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MURABAHA_NOT_SIGNED")

        contract = await self._get_signed_contract(order_id)
        if contract is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MURABAHA_NOT_SIGNED")

        existing = await self.db.scalar(select(VirtualCard).where(VirtualCard.order_id == order_id, VirtualCard.deleted_at.is_(None)))
        if existing is not None:
            return existing

        loan = await self.db.scalar(select(Loan).where(Loan.order_id == order_id, Loan.deleted_at.is_(None)))
        pan = self._generate_pan()
        cvv = f"{randbelow(1000):03d}"
        now = datetime.now(timezone.utc)
        card = VirtualCard(
            order_id=order_id,
            user_id=order.user_id,
            issuer="stripe",
            issuer_card_id=f"card_{hashlib.sha256(f'{order_id}:{pan}'.encode()).hexdigest()[:24]}",
            masked_number=self._mask_pan(pan),
            card_expiry=(now + timedelta(days=365 * 3)).date(),
            authorized_amount=amount_pkr,
            loaded_amount=amount_pkr,
            mcc_lock="retail",
            merchant_lock=merchant_domain,
            charged_amount=0,
            is_used=False,
            status="active",
            issued_at=now,
            expires_at=now + timedelta(hours=settings.VCN_EXPIRY_HOURS),
            encrypted_pan=self._encrypt_value(pan),
            encrypted_cvv=self._encrypt_value(cvv),
        )
        self.db.add(card)

        transaction = PaymentTransaction(
            loan_id=loan.id if loan is not None else None,
            installment_id=None,
            user_id=order.user_id,
            payment_method_id=None,
            amount=amount_pkr,
            currency=settings.PAYMENT_CURRENCY,
            gateway="stripe",
            gateway_txn_id=f"vcn_{order_id}",
            gateway_response={"order_id": order_id, "merchant_domain": merchant_domain},
            status="success",
            reconciled_at=now,
        )
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(card)

        envelope = build_event_envelope(
            event=EVENT_VCN_ISSUED,
            source_service="payment-orchestrator",
            payload={
                "order_id": order_id,
                "vcn_id": card.id,
                "status": card.status,
                "merchant_domain": merchant_domain,
            },
        )
        await self.redis.publish(event_channel(EVENT_VCN_ISSUED), envelope.to_json())
        return card

    async def queue_issue(self, *, order_id: int, amount_pkr: float, merchant_domain: str | None = None) -> None:
        await self.redis.rpush(
            QueueName.VCN_ISSUE,
            json.dumps({"order_id": order_id, "amount_pkr": amount_pkr, "merchant_domain": merchant_domain}),
        )

    async def confirm_down_payment(self, *, order_id: int, amount_pkr: float, gateway_txn_id: str) -> Loan:
        from decimal import Decimal
        order = await self._get_order(order_id)
        if order.status not in {OrderState.CONTRACTS_SIGNED, OrderState.DOWN_PAYMENT_PENDING, OrderState.DOWN_PAYMENT_RECEIVED}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ORDER_NOT_READY_FOR_PAYMENT")

        contract = await self._get_signed_contract(order_id)
        if contract is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MURABAHA_NOT_SIGNED")

        loan = await self.db.scalar(select(Loan).where(Loan.order_id == order_id, Loan.deleted_at.is_(None)))
        if loan is None:
            # Financed amount is Total Sale Price - Down Payment
            total_sale_price = Decimal(str(contract.total_sale_price))
            down_payment_received = Decimal(str(amount_pkr))
            balance_financed = total_sale_price - down_payment_received

            loan = Loan(
                order_id=order_id,
                user_id=order.user_id,
                murabaha_contract_id=contract.id,
                loan_number=f"SAK-LOAN-{order_id:010d}",
                principal_amount=contract.cost_price,
                profit_amount=contract.profit_amount,
                total_repayable=total_sale_price,
                down_payment_amount=down_payment_received,
                balance_financed=balance_financed,
                profit_rate_pct=contract.profit_rate_pct,
                plan_type="murabaha_installment",
                installment_count=contract.installment_count,
                installment_amount=total_sale_price / contract.installment_count,
                status="active",
                total_paid=down_payment_received,
                total_outstanding=balance_financed,
                late_fee_total=Decimal("0.00"),
            )
            self.db.add(loan)
            await self.db.flush()

            # Create the down payment installment record (already paid)
            installment = Installment(
                loan_id=loan.id,
                user_id=order.user_id,
                installment_number=0,  # 0 for down payment
                is_down_payment=True,
                principal_portion=down_payment_received,
                profit_portion=Decimal("0.00"),
                total_amount=down_payment_received,
                due_date=datetime.now(timezone.utc).date(),
                status="paid",
                paid_amount=down_payment_received,
                paid_at=datetime.now(timezone.utc),
                days_overdue=0,
                late_fee_amount=Decimal("0.00"),
                late_fee_waived=True,
                retry_count=0,
            )
            self.db.add(installment)

            # Create future installments based on the schedule if applicable
            # (In a real system, we'd parse contract.installment_schedule)
            # For now, we seed the first future installment if count > 0
            if contract.installment_count > 0:
                for i in range(1, contract.installment_count + 1):
                    future_inst = Installment(
                        loan_id=loan.id,
                        user_id=order.user_id,
                        installment_number=i,
                        is_down_payment=False,
                        principal_portion=balance_financed / contract.installment_count,
                        profit_portion=Decimal("0.00"), # Simplification: profit usually spread
                        total_amount=total_sale_price / contract.installment_count,
                        due_date=(datetime.now(timezone.utc) + timedelta(days=30 * i)).date(),
                        status="pending",
                        paid_amount=Decimal("0.00"),
                    )
                    self.db.add(future_inst)

        order.status = OrderState.DOWN_PAYMENT_RECEIVED
        await self.db.commit()

        envelope = build_event_envelope(
            event=EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED,
            source_service="payment-orchestrator",
            payload={
                "order_id": order_id,
                "amount_pkr": float(amount_pkr),
                "gateway_txn_id": gateway_txn_id,
            },
        )
        await self.redis.publish(event_channel(EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED), envelope.to_json())
        return loan

    async def _get_order(self, order_id: int) -> Order:
        order = await self.db.scalar(select(Order).where(Order.id == order_id, Order.deleted_at.is_(None)))
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
        return order

    async def _get_signed_contract(self, order_id: int) -> Optional[MurabahaContract]:
        return await self.db.scalar(
            select(MurabahaContract).where(MurabahaContract.order_id == order_id, MurabahaContract.signed_at.is_not(None))
        )

    async def _get_contract_id(self, order_id: int) -> Optional[int]:
        contract = await self._get_signed_contract(order_id)
        return contract.id if contract is not None else None

    def _generate_pan(self) -> str:
        digits = [4, 4, 4, 4]
        parts = []
        for size in digits:
            parts.append("".join(str(randbelow(10)) for _ in range(size)))
        return "".join(parts)

    def _mask_pan(self, pan: str) -> str:
        return f"**** **** **** {pan[-4:]}"

    def _encrypt_value(self, value: str) -> bytes:
        secret = settings.VCN_ENCRYPTION_KEY or settings.STRIPE_SECRET_KEY or "mock-vcn-key"
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key).encrypt(value.encode("utf-8"))
