import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser, User
from sk_shared.models.contracts import MurabahaContract, WakalahAgreement
from sk_shared.models.order import Order
from sk_shared.redis_client import RedisClient
from sk_shared.storage import get_storage_client
from src.config import settings
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_current_user, get_db, get_redis
from src.core.logging import logger
from src.schemas.contracts import (
    ContractDisclosure,
    ContractSignResponse,
    ContractStatusResponse,
    MurabahaGenerateRequest,
    MurabahaGenerateResponse,
    MurabahaSignRequest,
    WakalahGenerateRequest,
    WakalahGenerateResponse,
    WakalahSignRequest,
)
from src.services.contract_generator import ContractGeneratorService
from src.services.contract_signer import ContractSignerService

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.post("/wakalah/generate", response_model=WakalahGenerateResponse)
async def generate_wakalah(
    req: WakalahGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    contract = await ContractGeneratorService(db).generate_wakalah(current_user.id, req, redis)
    # SEC-10: Prefer decrypted principal_name from encrypted field; fall back to cleartext
    principal_name = contract.principal_name
    if getattr(contract, "principal_name_encrypted", None):
        try:
            from src.core.kms import KMSProvider
            principal_name = KMSProvider().decrypt(contract.principal_name_encrypted)
        except Exception:
            pass
    return WakalahGenerateResponse(
        contract_id=contract.id,
        contract_number=contract.contract_number,
        principal_name=principal_name,
        agent_name=contract.agent_name,
        authorized_amount=float(contract.authorized_amount),
        valid_until=contract.valid_until,
        otp_sent=True,
        dev_otp=getattr(contract, "_dev_otp", None),
    )


@router.post("/wakalah/sign", response_model=ContractSignResponse)
async def sign_wakalah(
    req: WakalahSignRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    contract, order = await ContractSignerService.sign_wakalah(
        db=db,
        redis=redis,
        user_id=current_user.id,
        contract_id=req.contract_id,
        otp_code=req.otp_code,
        ip_address=request.client.host if request.client else None,
        device_id=req.device_id,
    )
    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="contracts",
        action="sign_wakalah",
        target_id=contract.id,
        changes={"order_id": order.id, "contract_number": contract.contract_number},
    )
    await db.commit()
    await db.refresh(contract)
    await db.refresh(order)
    return ContractSignResponse(signed=True, signed_at=contract.signed_at, order_status=order.status)


@router.post("/murabaha/generate", response_model=MurabahaGenerateResponse)
async def generate_murabaha(
    req: MurabahaGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    # GW-BL-03: Enforce Wakalah signed before Murabaha generation
    wakalah = await db.scalar(
        select(WakalahAgreement).where(
            WakalahAgreement.order_id == req.order_id,
            WakalahAgreement.user_id == current_user.id,
            WakalahAgreement.signed_at.is_not(None),
            WakalahAgreement.deleted_at.is_(None),
        )
    )
    if not wakalah:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="WAKALAH_NOT_SIGNED"
        )

    contract = await ContractGeneratorService(db).generate_murabaha(current_user.id, req, redis)
    return MurabahaGenerateResponse(
        contract_id=contract.id,
        contract_number=contract.contract_number,
        disclosure=ContractDisclosure(
            cost_price=float(contract.cost_price),
            profit_amount=float(contract.profit_amount),
            total_sale_price=float(contract.total_sale_price),
            profit_rate_pct=float(contract.profit_rate_pct),
            currency=getattr(contract, "currency", "PKR"),
            installment_count=contract.installment_count,
        ),
        otp_sent=True,
        dev_otp=getattr(contract, "_dev_otp", None),
    )


@router.post("/murabaha/sign", response_model=ContractSignResponse)
async def sign_murabaha(
    req: MurabahaSignRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    if not req.confirmation_checkbox:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CONFIRMATION_REQUIRED")

    contract, order, pending_event = await ContractSignerService.sign_murabaha(
        db=db,
        redis=redis,
        user_id=current_user.id,
        contract_id=req.contract_id,
        otp_code=req.otp_code,
        ip_address=request.client.host if request.client else None,
        device_id=req.device_id,
    )
    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="contracts",
        action="sign_murabaha",
        target_id=contract.id,
        changes={"order_id": order.id, "contract_number": contract.contract_number},
    )
    await db.commit()
    await db.refresh(contract)
    await db.refresh(order)

    # HIGH-1 fix: publish EVENT_LOAN_CREATED only now that the loan/installments
    # are durably committed -- publishing before commit let a fast consumer
    # (e.g. Ledger Service) query for a loan that didn't exist yet in the DB.
    # Best-effort: a publish failure here must not fail the (already-committed)
    # sign request back to the customer.
    if pending_event is not None:
        channel, message = pending_event
        try:
            await redis.publish(channel, message)
        except Exception:
            logger.error(
                "Failed to publish loan.created event after commit order_id=%s contract_id=%s",
                order.id, contract.id, exc_info=True,
            )

    return ContractSignResponse(signed=True, signed_at=contract.signed_at, order_status=order.status)




# --- Admin Routes ---


@router.get("/admin/wakalah")
async def list_wakalah(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    user_id: int | None = Query(default=None),
    signed: bool | None = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    stmt = select(WakalahAgreement).where(WakalahAgreement.deleted_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(WakalahAgreement.user_id == user_id)
    if signed is not None:
        stmt = stmt.where(WakalahAgreement.signed_at.is_not(None) if signed else WakalahAgreement.signed_at.is_(None))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        await db.execute(stmt.order_by(WakalahAgreement.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return {
        "items": rows,
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/admin/murabaha")
async def list_murabaha(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    user_id: int | None = Query(default=None),
    signed: bool | None = Query(default=None),
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    stmt = select(MurabahaContract).where(MurabahaContract.deleted_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(MurabahaContract.user_id == user_id)
    if signed is not None:
        stmt = stmt.where(MurabahaContract.signed_at.is_not(None) if signed else MurabahaContract.signed_at.is_(None))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        await db.execute(stmt.order_by(MurabahaContract.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return {
        "items": rows,
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/admin/{contract_type}/{contract_id}/pdf")
async def get_contract_pdf(
    contract_id: int,
    contract_type: str,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("read_order")),
    db: AsyncSession = Depends(get_db),
):
    model = WakalahAgreement if contract_type == "wakalah" else MurabahaContract
    contract = await db.scalar(select(model).where(model.id == contract_id))
    if not contract:
        raise HTTPException(status_code=404, detail="CONTRACT_NOT_FOUND")

    storage = get_storage_client(settings)
    raw_path = str(contract.contract_pdf_path)
    key = raw_path
    if raw_path.startswith("s3://"):
        parts = raw_path.split("/", 3)
        key = parts[3] if len(parts) > 3 else ""

    if hasattr(storage, "base_dir") and Path(raw_path).exists():
        download_url = f"file://{Path(raw_path).absolute()}"
    else:
        download_url = await storage.get_download_url(key, expires_in=900)

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="contracts",
        action="admin_contract_pdf_accessed",
        target_id=contract_id,
        changes={"contract_type": contract_type},
    )
    await db.commit()

    return {
        "pdf_path": contract.contract_pdf_path,
        "download_url": download_url,
        "expires_in": 900,
    }


@router.get("/{contract_type}/{contract_id}/download")
async def download_contract_pdf(
    contract_type: str,
    contract_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MISS-05: Customer-facing contract PDF download via pre-signed URL."""
    if contract_type not in ("wakalah", "murabaha"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_CONTRACT_TYPE")

    model = WakalahAgreement if contract_type == "wakalah" else MurabahaContract
    contract = await db.scalar(
        select(model).where(
            model.id == contract_id,
            model.user_id == current_user.id,
            model.deleted_at.is_(None),
        )
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONTRACT_NOT_FOUND")
    if not contract.signed_at:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CONTRACT_NOT_YET_SIGNED")

    storage = get_storage_client(settings)
    raw_path = str(contract.contract_pdf_path)
    key = raw_path
    if raw_path.startswith("s3://"):
        parts = raw_path.split("/", 3)
        key = parts[3] if len(parts) > 3 else ""

    if hasattr(storage, "base_dir") and Path(raw_path).exists():
        download_url = f"file://{Path(raw_path).absolute()}"
    else:
        download_url = await storage.get_download_url(key, expires_in=900)

    return {"contract_id": contract_id, "contract_type": contract_type, "download_url": download_url, "expires_in": 900}


@router.get("/{order_id}", response_model=ContractStatusResponse)
async def get_contract_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(select(Order).where(Order.id == order_id, Order.user_id == current_user.id))
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    wakalah = await db.scalar(
        select(WakalahAgreement).where(
            WakalahAgreement.order_id == order_id,
            WakalahAgreement.user_id == current_user.id,
            WakalahAgreement.deleted_at.is_(None),
        )
    )
    murabaha = await db.scalar(
        select(MurabahaContract).where(
            MurabahaContract.order_id == order_id,
            MurabahaContract.user_id == current_user.id,
            MurabahaContract.deleted_at.is_(None),
        )
    )

    return ContractStatusResponse(
        order_id=order.id,
        order_status=order.status,
        wakalah_signed=bool(wakalah and wakalah.signed_at),
        murabaha_signed=bool(murabaha and murabaha.signed_at),
        wakalah_contract_id=wakalah.id if wakalah else None,
        murabaha_contract_id=murabaha.id if murabaha else None,
        financial_summary=ContractDisclosure(
            cost_price=float(murabaha.cost_price),
            profit_amount=float(murabaha.profit_amount),
            total_sale_price=float(murabaha.total_sale_price),
            profit_rate_pct=float(murabaha.profit_rate_pct),
            currency=getattr(murabaha, "currency", "PKR"),
            installment_count=murabaha.installment_count,
        )
        if murabaha
        else None,
    )


@router.get("/{contract_type}/{contract_id}/verify")
async def verify_contract_integrity(
    contract_type: str,
    contract_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = WakalahAgreement if contract_type == "wakalah" else MurabahaContract
    contract = await db.scalar(
        select(model).where(model.id == contract_id, model.user_id == current_user.id, model.deleted_at.is_(None))
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONTRACT_NOT_FOUND")

    storage = get_storage_client(settings)
    if hasattr(storage, "base_dir"):
        path = Path(contract.contract_pdf_path)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CONTRACT_FILE_NOT_FOUND")
        computed_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        try:
            pdf_bytes = await storage.download(contract.contract_pdf_path)
            computed_hash = hashlib.sha256(pdf_bytes).hexdigest()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"CONTRACT_FETCH_FAILED: {exc}")
    return {
        "valid": computed_hash == contract.contract_hash,
        "stored_hash": contract.contract_hash,
        "computed_hash": computed_hash,
    }
