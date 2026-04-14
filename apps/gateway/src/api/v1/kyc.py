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

router = APIRouter(prefix="/kyc", tags=["KYC"])


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

    # Mock local-storage path; swap for S3 presigned URL in production.
    file_path = f"/tmp/kyc/{current_user.id}/{document_type}_{file.filename}"

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
    return profile


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
    return profile
