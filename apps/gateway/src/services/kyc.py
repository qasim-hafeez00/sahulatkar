from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from sk_shared.models.kyc import (
    CustomerProfile,
    KycStatus,
    KycVerificationQueue,
    UserKycVerification,
)
from src.schemas.kyc import CustomerProfileBase
from .nadra import NadraClientMock
from .shufti import ShuftiClientMock


class KycService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.nadra_client = NadraClientMock()
        self.shufti_client = ShuftiClientMock()

    # ── KYC Verification ─────────────────────────────────────────────────────

    async def get_or_create_kyc(self, user_id: int) -> UserKycVerification:
        result = await self.db.execute(
            select(UserKycVerification).where(UserKycVerification.user_id == user_id)
        )
        kyc = result.scalar_one_or_none()
        if not kyc:
            kyc = UserKycVerification(user_id=user_id, status=KycStatus.PENDING)
            self.db.add(kyc)
            await self.db.commit()
            await self.db.refresh(kyc)
        return kyc

    async def upload_document(
        self, user_id: int, document_type: str, file_path: str
    ) -> UserKycVerification:
        kyc = await self.get_or_create_kyc(user_id)

        match document_type:
            case "cnic_front":
                kyc.cnic_front_image_url = file_path
            case "cnic_back":
                kyc.cnic_back_image_url = file_path
            case "liveness_video":
                kyc.liveness_video_url = file_path

        await self.db.commit()
        await self.db.refresh(kyc)
        return kyc

    async def submit_for_verification(self, user_id: int) -> UserKycVerification:
        kyc = await self.get_or_create_kyc(user_id)

        missing = []
        if not kyc.cnic_front_image_url:
            missing.append("cnic_front")
        if not kyc.cnic_back_image_url:
            missing.append("cnic_back")
        if not kyc.liveness_video_url:
            missing.append("liveness_video")
        if missing:
            raise ValueError(f"Missing required documents: {', '.join(missing)}")

        kyc.status = KycStatus.SUBMITTED
        await self.db.commit()

        # --- Automated checks (mock) ---
        ocr_result = await self.shufti_client.verify_document(
            kyc.cnic_front_image_url, kyc.cnic_back_image_url
        )
        liveness_result = await self.shufti_client.verify_liveness(kyc.liveness_video_url)

        kyc.shufti_verification_data = {
            "ocr": ocr_result,
            "liveness": liveness_result,
        }

        if not ocr_result.get("success") or not liveness_result.get("success"):
            kyc.status = KycStatus.REJECTED
            reasons = []
            if not ocr_result.get("success"):
                reasons.append(ocr_result.get("reason", "OCR failed"))
            if not liveness_result.get("success"):
                reasons.append(liveness_result.get("reason", "Liveness check failed"))
            kyc.rejection_reason = "; ".join(reasons)
            await self.db.commit()
            await self.db.refresh(kyc)
            return kyc

        # --- NADRA CNIC check ---
        extracted_cnic = (
            (ocr_result.get("extracted_data") or {}).get("cnic") or "12345-1234567-1"
        )
        nadra_ok = await self.nadra_client.verify_cnic(extracted_cnic)
        kyc.nadra_verification_data = {"success": nadra_ok, "verified_cnic": extracted_cnic}

        if not nadra_ok:
            kyc.status = KycStatus.REJECTED
            kyc.rejection_reason = "NADRA verification failed for CNIC."
        else:
            kyc.status = KycStatus.IN_REVIEW
            # Push to manual review queue (idempotent via unique constraint)
            existing_q = await self.db.execute(
                select(KycVerificationQueue).where(
                    KycVerificationQueue.kyc_verification_id == kyc.id
                )
            )
            if not existing_q.scalar_one_or_none():
                self.db.add(KycVerificationQueue(kyc_verification_id=kyc.id))

        await self.db.commit()
        await self.db.refresh(kyc)
        return kyc

    # ── Customer Profile ──────────────────────────────────────────────────────

    async def get_profile(self, user_id: int) -> CustomerProfile | None:
        result = await self.db.execute(
            select(CustomerProfile).where(CustomerProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_profile(
        self, user_id: int, payload: CustomerProfileBase
    ) -> CustomerProfile:
        profile = await self.get_profile(user_id)
        if profile is None:
            profile = CustomerProfile(user_id=user_id)
            self.db.add(profile)

        profile.first_name = payload.first_name
        profile.last_name = payload.last_name
        profile.cnic = payload.cnic
        profile.dob = payload.dob
        profile.address = payload.address

        await self.db.commit()
        await self.db.refresh(profile)
        return profile
