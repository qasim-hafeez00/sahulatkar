from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from sk_shared.models.ledger import CharityOrganization, LedgerAccount
from src.core.database import get_db


router = APIRouter()


class HealthStatusResponse(BaseModel):
    status: str
    service: str = Field(default="ledger-service")


class ReadinessResponse(BaseModel):
    status: str
    dependencies: dict[str, bool]
    checks: dict[str, int]
    listeners: dict[str, bool]


@router.get("/health/live", response_model=HealthStatusResponse)
async def liveness() -> HealthStatusResponse:
    return HealthStatusResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(request: Request, db: AsyncSession = Depends(get_db)) -> ReadinessResponse:
    db_ok = False
    redis_ok = False
    ledger_accounts_count = 0
    active_charities_count = 0

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    if db_ok:
        ledger_accounts_count = int((await db.execute(select(func.count(LedgerAccount.id)))).scalar_one())
        active_charities_count = int(
            (await db.execute(select(func.count(CharityOrganization.id)).where(CharityOrganization.is_active.is_(True)))).scalar_one()
        )

    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        try:
            pong = await redis_client.redis.ping()
            redis_ok = bool(pong)
        except Exception:
            redis_ok = False

    all_ok = db_ok and redis_ok and ledger_accounts_count > 0 and active_charities_count > 0
    listener_task = getattr(request.app.state, "ledger_event_task", None)
    watchdog_task = getattr(request.app.state, "ledger_event_watchdog_task", None)
    listener_ok = bool(listener_task and not listener_task.done())
    watchdog_ok = bool(watchdog_task and not watchdog_task.done())

    return ReadinessResponse(
        status="ready" if all_ok else "degraded",
        dependencies={
            "database": db_ok,
            "redis": redis_ok,
            "ledger_accounts_seeded": ledger_accounts_count > 0,
            "active_charity_configured": active_charities_count > 0,
        },
        checks={
            "ledger_accounts": ledger_accounts_count,
            "active_charities": active_charities_count,
        },
        listeners={
            "ledger_event_listener": listener_ok,
            "ledger_event_watchdog": watchdog_ok,
        },
    )
