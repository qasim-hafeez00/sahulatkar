from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import get_redis
from sk_shared.redis_client import RedisClient
from src.services.accounting_service import AccountingService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("/")
async def list_accounts(
    account_type: str | None = Query(None, regex="^(asset|liability|equity|revenue|expense)$"),
    as_of: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """List all GL accounts with their current balances."""
    service = AccountingService(db, redis=redis)
    return await service.list_accounts(account_type=account_type, as_of=as_of)


@router.get("/{account_code}")
async def get_account_details(
    account_code: str,
    as_of: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get detailed information and balance for a specific account."""
    service = AccountingService(db, redis=redis)
    try:
        return await service.get_account_balance(account_code, as_of=as_of)
    except LookupError:
        raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND")

@router.get("/{account_code}/ledger")
async def get_account_ledger(
    account_code: str,
    from_date: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get the full ledger (T-account view) for an account."""
    service = AccountingService(db, redis=redis)
    try:
        return await service.get_account_ledger(
            account_code=account_code,
            from_date=from_date,
            to_date=to_date,
            cursor=cursor,
            limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
