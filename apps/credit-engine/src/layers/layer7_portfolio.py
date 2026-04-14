from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.credit import CreditApplication


async def run_portfolio_concentration(
    db: AsyncSession,
    user_id: str,
    requested_amount: float,
    maximum_limit: float,
) -> tuple[bool, Optional[str], list[str]]:
    flags: list[str] = []
    user_uuid = UUID(user_id)

    current_limit_stmt = select(func.coalesce(func.max(CreditApplication.approved_limit), Decimal("0"))).where(
        CreditApplication.user_id == user_uuid,
        CreditApplication.status == "approved",
    )
    current_limit = float((await db.execute(current_limit_stmt)).scalar_one())

    projected_exposure = current_limit + requested_amount
    if projected_exposure > maximum_limit:
        return True, "Requested amount breaches portfolio exposure limit", ["portfolio_limit_exceeded"]

    utilization_ratio = projected_exposure / maximum_limit if maximum_limit else 1.0
    if utilization_ratio > 0.8:
        flags.append("high_utilization")

    return False, None, flags
