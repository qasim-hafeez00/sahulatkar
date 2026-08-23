from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState, RedisNS
from sk_shared.models.auth import User
from sk_shared.models.contracts import ContractDigitalSignature, MurabahaContract, WakalahAgreement
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.redis_client import RedisClient
from sk_shared.security import generate_otp, hash_otp
from src.config import settings
from src.services.notify import notify


class ContractSignerService:
    @staticmethod
    async def issue_signing_otp(db: AsyncSession, redis: RedisClient, contract_type: str, contract_id: int, user_id: int) -> str | None:
        # Fetch user phone number for the notification
        model = WakalahAgreement if contract_type == "wakalah" else MurabahaContract
        contract = await db.scalar(select(model).where(model.id == contract_id))
        if not contract:
            return None

        user = await db.scalar(select(User).where(User.id == contract.user_id))
        if not user or not user.phone:
            return None

        otp = generate_otp()
        otp_hash = hash_otp(otp)
        otp_key = f"{RedisNS.CONTRACT_OTP}:{contract_type}:{contract_id}:{user_id}"
        attempts_key = f"{RedisNS.CONTRACT_OTP_ATTEMPTS}:{contract_type}:{contract_id}:{user_id}"

        await redis.set(otp_key, otp_hash, settings.OTP_TTL)
        await redis.delete(attempts_key)

        if settings.NOTIFICATION_SMS_ENABLED:
            from src.core.http_client import InternalServiceClient
            await InternalServiceClient.send_otp(
                phone=user.phone, otp_code=otp, purpose="contract_sign", expires_in_seconds=settings.OTP_TTL,
            )

        # DEV ONLY: let callers surface the code directly (mirrors AuthService's
        # register/otp dev_otp) since there's no SMS gateway in local/dev envs.
        return None if settings.ENVIRONMENT == "production" else otp

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
        from sk_shared.models.cart import CartItem
        from datetime import timedelta
        import uuid

        # Cart-aware unified financing: a cart's line items are separate Orders each
        # with their own Murabaha contract (Islamic finance requires a Murabaha sale
        # to identify a specific underlying asset), but they share ONE combined Loan
        # and repayment schedule. If this order isn't part of a cart, sibling_order_ids
        # is just [order.id] and the block below behaves exactly as the single-order
        # flow always has.
        cart_item = await db.scalar(select(CartItem).where(CartItem.order_id == order.id))
        sibling_order_ids = [order.id]
        if cart_item is not None:
            sibling_items = (
                await db.execute(select(CartItem).where(CartItem.cart_id == cart_item.cart_id))
            ).scalars().all()
            sibling_order_ids = [i.order_id for i in sibling_items]

        sibling_contracts = (
            await db.execute(
                select(MurabahaContract).where(MurabahaContract.order_id.in_(sibling_order_ids))
            )
        ).scalars().all()

        # Not every sibling order in the cart is guaranteed to have generated (let
        # alone signed) its Murabaha contract yet — the frontend signs them one at a
        # time. Only consolidate into a Loan once every sibling has signed.
        all_signed = (
            len(sibling_contracts) == len(sibling_order_ids)
            and all(c.signed_at is not None for c in sibling_contracts)
        )
        if not all_signed:
            await db.flush()
            return contract, order

        sibling_orders = (
            await db.execute(select(Order).where(Order.id.in_(sibling_order_ids)))
        ).scalars().all()
        orders_by_id = {o.id: o for o in sibling_orders}

        total_cost_price = sum(float(c.cost_price) for c in sibling_contracts)
        total_profit_amount = sum(float(c.profit_amount) for c in sibling_contracts)
        total_sale_price = sum(float(c.total_sale_price) for c in sibling_contracts)
        down_payment = sum(float(orders_by_id[c.order_id].down_payment_amount or 0) for c in sibling_contracts)
        total_repayable = round(total_sale_price - down_payment, 2)
        principal_amt = total_cost_price - down_payment
        installment_amt = round(total_repayable / contract.installment_count, 2)
        primary_order_id = min(sibling_order_ids)

        loan = Loan(
            order_id=primary_order_id,
            user_id=user_id,
            murabaha_contract_id=contract.id,
            loan_number=f"L-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:8].upper()}",
            principal_amount=principal_amt,
            profit_amount=total_profit_amount,
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

        # Every order in the group (all siblings, or just this one) resolves the
        # shared loan via orders.loan_id — independent of which order loans.order_id
        # happens to point at.
        for sibling_order in sibling_orders:
            sibling_order.loan_id = loan.id

        # Credit is already reserved at extraction (internal callback).
        # Loan creation consumes that reservation; no further decrement needed here.

        for n in range(1, contract.installment_count + 1):
            inst = Installment(
                loan_id=loan.id,
                user_id=user_id,
                installment_number=n,
                is_down_payment=False,
                principal_portion=principal_amt / contract.installment_count,
                profit_portion=total_profit_amount / contract.installment_count,
                total_amount=installment_amt,
                due_date=(datetime.now(timezone.utc) + timedelta(days=30 * n)).date(),
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

        await notify(
            db, user_id, "credit",
            "Financing approved",
            f"Your Murabaha financing (Loan {loan.loan_number}) for PKR {total_repayable:,.0f} across {contract.installment_count} installments has been approved.",
            source_event="loan.created", source_reference=f"loan:{loan.id}",
        )

        return contract, order
