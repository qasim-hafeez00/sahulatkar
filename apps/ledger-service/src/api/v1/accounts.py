from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.accounting_service import AccountingService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/")
async def list_accounts(
    account_type: str | None = Query(None, regex="^(asset|liability|equity|revenue|expense)$"),
    as_of: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
):
    """List all GL accounts with their current balances."""
    service = AccountingService(db)
    return await service.list_accounts(account_type=account_type, as_of=as_of)


@router.get("/{account_code}")
async def get_account_details(
    account_code: str,
    as_of: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information and balance for a specific account."""
    service = AccountingService(db)
    try:
        return await service.get_account_balance(account_code, as_of=as_of)
    except LookupError:
        raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND")
