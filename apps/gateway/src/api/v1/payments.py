from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import OrderState
from sk_shared.models.auth import User
from sk_shared.models.order import Order
from src.core.dependencies import get_current_user, get_db
from src.schemas.payments import VcnIssueRequest, VcnIssueResponse

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/vcn/issue", response_model=VcnIssueResponse)
async def issue_vcn(
    req: VcnIssueRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(
        select(Order).where(
            Order.id == req.order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    if order.status != OrderState.CONTRACTS_SIGNED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MURABAHA_NOT_SIGNED")

    return VcnIssueResponse(status="queued", order_id=order.id)
