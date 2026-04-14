from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser, User
from sk_shared.models.contracts import MurabahaContract, WakalahAgreement
from sk_shared.models.order import Order
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_current_admin, get_current_user, get_db, get_redis
from src.schemas.contracts import (
    AdminContractResponse,
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
    return WakalahGenerateResponse(
        contract_id=contract.id,
        contract_number=contract.contract_number,
        principal_name=contract.principal_name,
        agent_name=contract.agent_name,
        authorized_amount=float(contract.authorized_amount),
        valid_until=contract.valid_until,
        otp_sent=True,
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
    return ContractSignResponse(signed=True, signed_at=contract.signed_at, order_status=order.status)


@router.post("/murabaha/generate", response_model=MurabahaGenerateResponse)
async def generate_murabaha(
    req: MurabahaGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    contract = await ContractGeneratorService(db).generate_murabaha(current_user.id, req, redis)
    return MurabahaGenerateResponse(
        contract_id=contract.id,
        contract_number=contract.contract_number,
        disclosure=ContractDisclosure(
            cost_price=float(contract.cost_price),
            profit_amount=float(contract.profit_amount),
            total_sale_price=float(contract.total_sale_price),
            profit_rate_pct=float(contract.profit_rate_pct),
            currency=contract.currency,
            installment_count=contract.installment_count,
        ),
        otp_sent=True,
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

    contract, order = await ContractSignerService.sign_murabaha(
        db=db,
        redis=redis,
        user_id=current_user.id,
        contract_id=req.contract_id,
        otp_code=req.otp_code,
        ip_address=request.client.host if request.client else None,
        device_id=req.device_id,
    )
    return ContractSignResponse(signed=True, signed_at=contract.signed_at, order_status=order.status)


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
            currency=murabaha.currency,
            installment_count=murabaha.installment_count,
        )
        if murabaha
        else None,
    )


# --- Admin Routes ---


@router.get("/admin/wakalah", response_model=list[AdminContractResponse])
async def list_wakalah(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WakalahAgreement).order_by(WakalahAgreement.created_at.desc()).limit(100))
    return result.scalars().all()


@router.get("/admin/murabaha", response_model=list[AdminContractResponse])
async def list_murabaha(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MurabahaContract).order_by(MurabahaContract.created_at.desc()).limit(100))
    return result.scalars().all()


@router.get("/admin/{contract_type}/{contract_id}/pdf")
async def get_contract_pdf(
    contract_id: int,
    contract_type: str,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    model = WakalahAgreement if contract_type == "wakalah" else MurabahaContract
    contract = await db.scalar(select(model).where(model.id == contract_id))
    if not contract:
        raise HTTPException(status_code=404, detail="CONTRACT_NOT_FOUND")

    # In a real app, return a presigned S3 URL
    return {"pdf_path": contract.contract_pdf_path, "download_url": "https://s3.example.com/placeholder-presigned-url"}
