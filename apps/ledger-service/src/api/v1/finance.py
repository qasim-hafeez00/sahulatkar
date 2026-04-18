from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import RequestContext, require_admin_role, require_internal_request
from src.schemas.finance import (
    BalanceSheetResponse,
    CharityDisbursementRequest,
    CharityDisbursementResponse,
    CharityReportResponse,
    ProfitLossResponse,
    ReconciliationImportRequest,
    ReconciliationImportResponse,
    ReconciliationListResponse,
    ShariahAuditResponse,
    TrialBalanceResponse,
)
from src.services.accounting_service import AccountingService
from src.services.charity_service import CharityService
from src.services.reconciliation_service import ReconciliationService


router = APIRouter()


@router.get("/admin/finance/pl", response_model=ProfitLossResponse)
async def get_profit_loss(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db)
    try:
        return await service.build_profit_loss_report(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.get("/admin/finance/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db)
    try:
        return await service.get_trial_balance(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.get("/admin/finance/balance-sheet", response_model=BalanceSheetResponse)
async def get_balance_sheet(
    as_of: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db)
    try:
        return await service.build_balance_sheet(as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_AS_OF_DATE") from exc


@router.get("/admin/finance/reconciliation", response_model=ReconciliationListResponse)
async def get_reconciliation(
    gateway: str | None = Query(default=None),
    settlement_date: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = ReconciliationService(db)
    try:
        return await service.query_snapshots(gateway=gateway, settlement_date=settlement_date, page=page, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_SETTLEMENT_DATE") from exc


@router.get("/admin/finance/shariah-audit", response_model=ShariahAuditResponse)
async def get_shariah_audit(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db)
    try:
        return await service.build_shariah_audit_report(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.post("/admin/finance/reconciliation", response_model=ReconciliationImportResponse)
async def import_reconciliation(
    request: ReconciliationImportRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_request),
) -> dict[str, object]:
    service = ReconciliationService(db)
    return await service.import_snapshot(
        gateway=request.gateway,
        settlement_date=request.settlement_date.isoformat(),
        expected_amount=request.expected_amount,
        actual_amount=request.actual_amount,
        reference=request.reference,
        notes=request.notes,
    )


@router.get("/admin/finance/charity-report", response_model=CharityReportResponse)
async def get_charity_report(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = CharityService(db)
    try:
        return await service.get_charity_summary(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.post("/admin/finance/charity-disbursement", response_model=CharityDisbursementResponse)
async def post_charity_disbursement(
    request: CharityDisbursementRequest,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
) -> dict[str, object]:
    service = CharityService(db)
    return await service.record_disbursement(
        allocation_ids=request.allocation_ids,
        payment_reference=request.payment_reference,
        receipt_s3=request.receipt_s3,
    )