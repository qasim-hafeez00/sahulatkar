from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import RequestContext, get_request_context, require_internal_request
from src.services.accounting_service import AccountingService
from src.services.reconciliation_service import ReconciliationService


router = APIRouter()


class ReconciliationImportRequest(BaseModel):
    gateway: str = Field(..., examples=["safepay"])
    settlement_date: str
    expected_amount: Decimal
    actual_amount: Decimal
    reference: str | None = None
    notes: str | None = None


@router.get("/admin/finance/pl")
async def get_profit_loss(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(get_request_context),
) -> dict[str, object]:
    service = AccountingService(db)
    return await service.build_profit_loss_report(period)


@router.get("/admin/finance/reconciliation")
async def get_reconciliation(
    gateway: str | None = Query(default=None),
    settlement_date: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(get_request_context),
) -> dict[str, object]:
    service = ReconciliationService(db)
    return await service.query_snapshots(gateway=gateway, settlement_date=settlement_date, page=page, limit=limit)


@router.get("/admin/finance/shariah-audit")
async def get_shariah_audit(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(get_request_context),
) -> dict[str, object]:
    service = AccountingService(db)
    return await service.build_shariah_audit_report(period)


@router.post("/admin/finance/reconciliation")
async def import_reconciliation(
    request: ReconciliationImportRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_internal_request),
) -> dict[str, object]:
    service = ReconciliationService(db)
    return await service.import_snapshot(
        gateway=request.gateway,
        settlement_date=request.settlement_date,
        expected_amount=request.expected_amount,
        actual_amount=request.actual_amount,
        reference=request.reference,
        notes=request.notes,
    )