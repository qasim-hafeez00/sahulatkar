from __future__ import annotations

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from src.core.database import get_db
from src.core.dependencies import get_redis
from sk_shared.redis_client import RedisClient
from src.services.accounting_service import AccountingService

router = APIRouter(prefix="/entries", tags=["Journal Entries"])


class PostingLineSchema(BaseModel):
    account_code: str
    debit_amount: float = 0.0
    credit_amount: float = 0.0
    description: Optional[str] = None


class ManualEntryRequest(BaseModel):
    description: str
    lines: list[PostingLineSchema]
    entry_date: Optional[date] = None
    reference: Optional[str] = None


class ReversalRequest(BaseModel):
    reason: str
    reversal_id: Optional[str] = None
    entry_date: Optional[date] = None


@router.get("/")
async def list_journal_entries(
    from_date: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    to_date: str | None = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    entry_type: str | None = None,
    source_type: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Query journal entries with cursor-based pagination."""
    service = AccountingService(db, redis=redis)
    return await service.list_journal_entries(
        from_date=from_date,
        to_date=to_date,
        entry_type=entry_type,
        source_type=source_type,
        cursor=cursor,
        limit=limit
    )


@router.get("/{entry_number}")
async def get_entry(
    entry_number: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    """Get detailed information for a specific journal entry."""
    service = AccountingService(db, redis=redis)
    try:
        return await service.get_journal_entry(entry_number)
    except LookupError:
        raise HTTPException(status_code=404, detail="ENTRY_NOT_FOUND")


from src.core.rate_limit import rate_limit_admin_writes

@router.post("/manual")
async def create_manual_entry(
    req: ManualEntryRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    __: bool = Depends(rate_limit_admin_writes),
):
    """Create a manual journal entry (finance admin only)."""
    service = AccountingService(db, redis=redis)
    try:
        # Use idempotency key as reference if provided
        reference = idempotency_key or req.reference
        result = await service.record_manual_entry(
            lines=[line.model_dump() for line in req.lines],
            description=req.description,
            entry_date=req.entry_date,
            reference=reference
        )
        return {
            "entry_number": result.journal_entry.entry_number,
            "created": result.created
        }
    except LookupError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{entry_number}/reverse")
async def reverse_entry(
    entry_number: str,
    req: ReversalRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    __: bool = Depends(rate_limit_admin_writes),
):
    """Reverse an existing journal entry."""
    service = AccountingService(db, redis=redis)
    try:
        # Use idempotency key as reversal_id if provided
        reversal_id = idempotency_key or req.reversal_id or f"REV-{entry_number}"
        result = await service.record_reversal(
            reversal_id=reversal_id,
            original_entry_number=entry_number,
            reason=req.reason,
            entry_date=req.entry_date
        )
        return {
            "entry_number": result.journal_entry.entry_number,
            "created": result.created
        }
    except LookupError:
        raise HTTPException(status_code=404, detail="ORIGINAL_ENTRY_NOT_FOUND")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
