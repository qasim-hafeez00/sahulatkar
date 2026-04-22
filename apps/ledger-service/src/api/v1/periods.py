from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.core.database import get_db
from src.services.period_service import PeriodService

router = APIRouter(prefix="/periods", tags=["Periods"])


class PeriodCloseRequest(BaseModel):
    closed_by: str


@router.get("/")
async def list_periods(
    limit: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List accounting periods and their statuses."""
    service = PeriodService(db)
    periods = await service.list_periods(limit=limit)
    return [
        {
            "period_key": p.period_key,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat(),
            "status": p.status,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "closed_by": p.closed_by,
        }
        for p in periods
    ]


from src.core.rate_limit import rate_limit_admin_writes
from src.core.dependencies import get_redis
from sk_shared.redis_client import RedisClient

@router.post("/{period_key}/close")
async def close_period(
    period_key: str,
    req: PeriodCloseRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    __: bool = Depends(rate_limit_admin_writes),
):
    """Close an accounting period to prevent further postings."""
    service = PeriodService(db)
    try:
        period = await service.close_period(period_key, req.closed_by)
        await db.commit()
        return {"status": "closed", "period_key": period.period_key}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{period_key}/reopen")
async def reopen_period(
    period_key: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    __: bool = Depends(rate_limit_admin_writes),
):
    """Reopen a closed accounting period (use with caution)."""
    service = PeriodService(db)
    try:
        period = await service.reopen_period(period_key)
        await db.commit()
        return {"status": "open", "period_key": period.period_key}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
