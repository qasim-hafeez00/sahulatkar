from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, RedisNS
from sk_shared.models.auth import User
from sk_shared.models.contracts import ContractDigitalSignature, MurabahaContract, WakalahAgreement
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.notifications import NotificationClient
from sk_shared.redis_client import RedisClient
from sk_shared.security import generate_otp, hash_otp
from src.config import settings


class ContractSignerService:
    @staticmethod
    async def issue_signing_otp(db: AsyncSession, redis: RedisClient, contract_type: str, contract_id: int, user_id: int) -> None:
        # Fetch user phone number for the notification
        model = WakalahAgreement if contract_type == "wakalah" else MurabahaContract
        contract = await db.scalar(select(model).where(model.id == contract_id))
        if not contract:
            return

        user = await db.scalar(select(User).where(User.id == contract.user_id))
        if not user or not user.phone:
            return

        otp = generate_otp()
        otp_hash = hash_otp(otp)
        otp_key = f"{RedisNS.CONTRACT_OTP}:{contract_type}:{contract_id}:{user_id}"
        attempts_key = f"{RedisNS.CONTRACT_OTP_ATTEMPTS}:{contract_type}:{contract_id}:{user_id}"

        await redis.set(otp_key, otp_hash, settings.OTP_TTL)
        await redis.delete(attempts_key)

        # Inter-service notification via Redis queue
        if settings.NOTIFICATION_SMS_ENABLED:
            notify_backend = redis.redis if hasattr(redis, "redis") else redis
            notify = NotificationClient(notify_backend)
            await notify.push_contract_otp(user.phone, otp)

    @staticmethod
    async def verify_signing_otp(redis: RedisClient, contract_type: str, contract_id: int, user_id: int, otp_code: str) -> str:
        otp_key = f"{RedisNS.CONTRACT_OTP}:{contract_type}:{contract_id}:{user_id}"
        attempts_key = f"{RedisNS.CONTRACT_OTP_ATTEMPTS}:{contract_type}:{contract_id}:{user_id}"

        attempts = await redis.get(attempts_key)
        if attempts and int(attempts) >= settings.MAX_OTP_ATTEMPTS:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="TOO_MANY_ATTEMPTS")

        stored_hash = await redis.get(otp_key)
        if not stored_hash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP_EXPIRED")

        provided_hash = hash_otp(otp_code)
        if stored_hash != provided_hash:
            await redis.incr(attempts_key)
            await redis.expire(attempts_key, settings.OTP_ATTEMPTS_TTL)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OTP")

        await redis.delete(otp_key)
        await redis.delete(attempts_key)
        return provided_hash

    @staticmethod
    def _check_validity(contract: WakalahAgreement | MurabahaContract) -> None:
        if hasattr(contract, "valid_until") and contract.valid_until:
            valid_until = (
                contract.valid_until
                if contract.valid_until.tzinfo
                else contract.valid_until.replace(tzinfo=timezone.utc)
            )
            if datetime.now(timezone.utc) > valid_until:
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="CONTRACT_EXPIRED")

    @staticmethod
    async def sign_wakalah(
        db: AsyncSession,
        redis: RedisClient,
        user_id: int,
        contract_id: int,
        otp_code: str,
        ip_address: str | None,
        device_id: str | None,
    ) -> tuple[WakalahAgreement, Order]:
        result = await db.execute(
            select(WakalahAgreement).where(
                WakalahAgreement.id == contract_id,
                WakalahAgreement.user_id == user_id,
                WakalahAgreement.deleted_at.is_(None),
            ).with_for_update()
        )
        contract = result.scalar_one_or_none()
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WAKALAH_NOT_FOUND")
        if contract.signed_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_SIGNED")

        ContractSignerService._check_validity(contract)

        otp_hash = await ContractSignerService.verify_signing_otp(redis, "wakalah", contract.id, user_id, otp_code)

        order = await db.scalar(select(Order).where(Order.id == contract.order_id))
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

        old_status = order.status
        signed_at = datetime.now(timezone.utc)
        contract.signed_at = signed_at
        if old_status != OrderState.CONTRACTS_PENDING:
            order.status = OrderState.CONTRACTS_PENDING

        db.add(
            ContractDigitalSignature(
                wakalah_agreement_id=contract.id,
                user_id=user_id,
                signature_type="wakalah",
                ip_address=ip_address,
                device_id=device_id,
                otp_hash=otp_hash,
                signed_at=signed_at,
            )
        )
        if old_status != OrderState.CONTRACTS_PENDING:
            db.add(
                OrderStatusHistory(
                    order_id=order.id,
                    from_status=old_status,
                    to_status=OrderState.CONTRACTS_PENDING,
                    reason="wakalah_signed",
                )
            )

        await db.flush()
        return contract, order

    @staticmethod
    async def sign_murabaha(
        db: AsyncSession,
        redis: RedisClient,
        user_id: int,
        contract_id: int,
        otp_code: str,
        ip_address: str | None,
        device_id: str | None,
    ) -> tuple[MurabahaContract, Order]:
        result = await db.execute(
            select(MurabahaContract).where(
                MurabahaContract.id == contract_id,
                MurabahaContract.user_id == user_id,
                MurabahaContract.deleted_at.is_(None),
            ).with_for_update()
        )
        contract = result.scalar_one_or_none()
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MURABAHA_NOT_FOUND")
        if contract.signed_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_SIGNED")

        ContractSignerService._check_validity(contract)

        otp_hash = await ContractSignerService.verify_signing_otp(redis, "murabaha", contract.id, user_id, otp_code)

        order = await db.scalar(select(Order).where(Order.id == contract.order_id))
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

        old_status = order.status
        signed_at = datetime.now(timezone.utc)
        contract.signed_at = signed_at
        order.status = OrderState.CONTRACTS_SIGNED

        db.add(
            ContractDigitalSignature(
                murabaha_contract_id=contract.id,
                user_id=user_id,
                signature_type="murabaha",
                ip_address=ip_address,
                device_id=device_id,
                otp_hash=otp_hash,
                signed_at=signed_at,
            )
        )
        db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status=OrderState.CONTRACTS_SIGNED,
                reason="murabaha_signed",
            )
        )
        
        # P3-2: Automate Loan and Installment creation natively
        from sk_shared.models.payment import Loan, Installment
        from sk_shared.models.credit import CreditLimitHistory
        from datetime import timedelta
        import uuid

        down_payment = float(order.down_payment_amount or 0)
        total_sale = float(contract.total_sale_price)
        total_repayable = round(total_sale - down_payment, 2)
        principal_amt = float(contract.cost_price) - down_payment
        installment_amt = round(total_repayable / contract.installment_count, 2)

        loan = Loan(
            order_id=order.id,
            user_id=user_id,
            murabaha_contract_id=contract.id,
            loan_number=f"L-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:8].upper()}",
            principal_amount=principal_amt,
            profit_amount=float(contract.profit_amount),
            total_repayable=total_repayable,
            down_payment_amount=down_payment,
            balance_financed=principal_amt,
            profit_rate_pct=float(contract.profit_rate_pct),
            plan_type="murabaha",
            installment_count=contract.installment_count,
            installment_amount=installment_amt,
            total_paid=0.0,
            total_outstanding=total_repayable,
            late_fee_total=0.0,
            status="active",
        )
        db.add(loan)
        await db.flush()  # to get loan.id

        # Credit is already reserved at extraction (internal callback).
        # Loan creation consumes that reservation; no further decrement needed here.

        for sched in contract.installment_schedule:
            inst = Installment(
                loan_id=loan.id,
                user_id=user_id,
                installment_number=sched["installment_no"],
                is_down_payment=False,
                principal_portion=principal_amt / contract.installment_count,
                profit_portion=float(contract.profit_amount) / contract.installment_count,
                total_amount=float(sched["amount"]),  # already corrected in generator
                due_date=(datetime.now(timezone.utc) + timedelta(days=30 * sched["installment_no"])).date(),
                status="pending",
                paid_amount=0.0,
                days_overdue=0,
                late_fee_amount=0.0,
                late_fee_waived=False,
                retry_count=0,
            )
            db.add(inst)

        await db.flush()

        # Cross-Service: Publish loan.created so Ledger Service can post initial GL entries.
        from sk_shared.events import EVENT_LOAN_CREATED, build_event_envelope, event_channel
        envelope = build_event_envelope(
            event=EVENT_LOAN_CREATED,
            source_service="gateway",
            payload={
                "loan_id": loan.id,
                "order_id": order.id,
                "user_id": user_id,
                "principal_amount": float(loan.principal_amount),
                "profit_amount": float(loan.profit_amount),
                "total_repayable": float(loan.total_repayable),
                "installment_count": loan.installment_count,
            },
        )
        await redis.publish(event_channel(EVENT_LOAN_CREATED), envelope.to_json())

        return contract, order
