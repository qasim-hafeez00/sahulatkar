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
    async def issue_signing_otp(db: AsyncSession, redis: RedisClient, contract_type: str, contract_id: int) -> None:
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
        otp_key = f"{RedisNS.CONTRACT_OTP}:{contract_type}:{contract_id}"
        attempts_key = f"{RedisNS.CONTRACT_OTP_ATTEMPTS}:{contract_type}:{contract_id}"

        await redis.set(otp_key, otp_hash, settings.OTP_TTL)
        await redis.delete(attempts_key)

        # Inter-service notification via Redis queue
        if settings.NOTIFICATION_SMS_ENABLED:
            notify = NotificationClient(redis)
            await notify.push_contract_otp(user.phone, otp)

    @staticmethod
    async def verify_signing_otp(redis: RedisClient, contract_type: str, contract_id: int, otp_code: str) -> str:
        otp_key = f"{RedisNS.CONTRACT_OTP}:{contract_type}:{contract_id}"
        attempts_key = f"{RedisNS.CONTRACT_OTP_ATTEMPTS}:{contract_type}:{contract_id}"

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
            if datetime.now(timezone.utc) > contract.valid_until.replace(tzinfo=timezone.utc):
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
            )
        )
        contract = result.scalar_one_or_none()
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WAKALAH_NOT_FOUND")
        if contract.signed_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_SIGNED")

        ContractSignerService._check_validity(contract)

        otp_hash = await ContractSignerService.verify_signing_otp(redis, "wakalah", contract.id, otp_code)

        order = await db.scalar(select(Order).where(Order.id == contract.order_id))
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

        old_status = order.status
        signed_at = datetime.now(timezone.utc)
        contract.signed_at = signed_at
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
        db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status=OrderState.CONTRACTS_PENDING,
                reason="wakalah_signed",
            )
        )

        await db.commit()
        await db.refresh(contract)
        await db.refresh(order)
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
            )
        )
        contract = result.scalar_one_or_none()
        if contract is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MURABAHA_NOT_FOUND")
        if contract.signed_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_SIGNED")

        ContractSignerService._check_validity(contract)

        otp_hash = await ContractSignerService.verify_signing_otp(redis, "murabaha", contract.id, otp_code)

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

        await db.commit()
        await db.refresh(contract)
        await db.refresh(order)
        return contract, order
