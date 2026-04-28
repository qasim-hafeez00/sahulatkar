import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db, get_current_user
from src.schemas.kyc import (
    CustomerProfileBase,
    CustomerProfileResponse,
    KycVerificationResponse,
)
from src.services.kyc import KycService
from sk_shared.models.auth import User
from sk_shared.models.kyc import KycStatus
from sk_shared.storage import get_storage_client
from src.config import settings

router = APIRouter(prefix="/kyc", tags=["KYC"])
MAX_KYC_ATTEMPTS = 3


@router.post("/start", response_model=KycVerificationResponse, status_code=status.HTTP_200_OK)
async def start_kyc(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initialise a KYC record for the authenticated user (idempotent)."""
    service = KycService(db)
    kyc = await service.get_or_create_kyc(current_user.id)
    return kyc


@router.post("/upload/{document_type}", response_model=KycVerificationResponse)
async def upload_document(
    document_type: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a KYC document (cnic_front | cnic_back | liveness_video)."""
    allowed_types = {"cnic_front", "cnic_back", "liveness_video"}
    if document_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document_type. Allowed: {sorted(allowed_types)}",
        )

    file_key = f"kyc/{current_user.id}/{document_type}_{file.filename}"
    payload = await file.read()
    file_path = await get_storage_client(settings).upload(file_key, payload)

    service = KycService(db)
    kyc = await service.upload_document(current_user.id, document_type, file_path)
    return kyc


@router.post("/submit", response_model=KycVerificationResponse)
async def submit_kyc(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit all uploaded documents for automated + manual KYC review."""
    service = KycService(db)
    try:
        kyc = await service.submit_for_verification(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return kyc


@router.get("/status", response_model=KycVerificationResponse)
async def get_kyc_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current KYC verification status for the authenticated user."""
    service = KycService(db)
    kyc = await service.get_or_create_kyc(current_user.id)
    storage = get_storage_client(settings)
    for field in ["cnic_front_image_url", "cnic_back_image_url", "liveness_video_url"]:
        value = getattr(kyc, field, None)
        if value:
            setattr(kyc, field, await storage.get_download_url(value))
    return kyc


@router.post("/resubmit", response_model=KycVerificationResponse)
async def resubmit_kyc(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = KycService(db)
    kyc = await service.get_or_create_kyc(current_user.id)
    if kyc.status != KycStatus.REJECTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="KYC_NOT_REJECTED")
    if (kyc.attempt_number or 1) >= MAX_KYC_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="KYC_MAX_ATTEMPTS_REACHED: Contact support for manual review.",
        )

    kyc.status = KycStatus.PENDING
    kyc.attempt_number = (getattr(kyc, "attempt_number", 1) or 1) + 1
    kyc.rejection_reason = None
    if hasattr(kyc, "rejection_code"):
        kyc.rejection_code = None
    kyc.cnic_front_image_url = None
    kyc.cnic_back_image_url = None
    kyc.liveness_video_url = None
    
    # TASK-13: Clear stale NADRA/Shufti verification data on resubmit
    if hasattr(kyc, "nadra_verification_data"):
        kyc.nadra_verification_data = None
    if hasattr(kyc, "nadra_verified_at"):
        kyc.nadra_verified_at = None
    if hasattr(kyc, "shufti_verification_data"):
        kyc.shufti_verification_data = None
    
    from sqlalchemy import delete, select
    from sk_shared.models.kyc import KycVerificationQueue
    
    active_queue = await db.scalar(
        select(KycVerificationQueue).where(
            KycVerificationQueue.kyc_verification_id == kyc.id,
            KycVerificationQueue.assigned_admin_id.is_not(None)
        )
    )
    if active_queue:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PREVIOUS_ATTEMPT_STILL_CLAIMED"
        )
    
    await db.execute(
        delete(KycVerificationQueue).where(
            KycVerificationQueue.kyc_verification_id == kyc.id
        )
    )
    
    await db.commit()
    await db.refresh(kyc)
    return kyc


# ── Customer Profile ─────────────────────────────────────────────────────────

@router.put("/profile", response_model=CustomerProfileResponse)
async def upsert_profile(
    payload: CustomerProfileBase,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the customer's personal profile."""
    service = KycService(db)
    profile = await service.upsert_profile(current_user.id, payload)
    
    # Decrypt CNIC for the response to avoid Pydantic validation errors on bytes
    from src.core.kms import KMSProvider
    resp = {c.name: getattr(profile, c.name) for c in profile.__table__.columns}
    cnic_val = resp.get("cnic")
    if isinstance(cnic_val, (bytes, bytearray)):
        try:
            resp["cnic"] = KMSProvider().decrypt(cnic_val)
        except Exception:
            # Fallback for legacy or corrupted data
            try:
                resp["cnic"] = cnic_val.decode("utf-8")
            except Exception:
                resp["cnic"] = ""
        
    return resp


@router.get("/profile", response_model=CustomerProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the customer's personal profile."""
    service = KycService(db)
    profile = await service.get_profile(current_user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
        
    from src.core.kms import KMSProvider
    resp = {c.name: getattr(profile, c.name) for c in profile.__table__.columns}
    cnic_val = resp.get("cnic")
    if isinstance(cnic_val, (bytes, bytearray)):
        try:
            resp["cnic"] = KMSProvider().decrypt(cnic_val)
        except Exception:
            try:
                resp["cnic"] = cnic_val.decode("utf-8")
            except Exception:
                resp["cnic"] = ""
        
    return resp
