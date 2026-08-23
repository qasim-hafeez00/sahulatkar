from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.models.credit import CreditLimitHistory, RiskAssessment
from sk_shared.models.payment import Loan
from src.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/credit", tags=["credit"])


@router.get("/status")
async def credit_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Refresh from DB to ensure latest credit numbers (GAP-13)
    fresh_user = await db.scalar(select(User).where(User.id == current_user.id, User.deleted_at.is_(None)))
    if fresh_user:
        current_user = fresh_user

    latest_risk = await db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.user_id == current_user.id)
        .order_by(RiskAssessment.created_at.desc())
    )
    latest_limit = await db.scalar(
        select(CreditLimitHistory)
        .where(CreditLimitHistory.user_id == current_user.id)
        .order_by(CreditLimitHistory.created_at.desc())
    )

    active_loans = (
        await db.execute(
            select(Loan).where(Loan.user_id == current_user.id, Loan.deleted_at.is_(None), Loan.status == "active")
        )
    ).scalars().all()
    outstanding = sum(float(loan.total_outstanding or 0) for loan in active_loans)

    # Use fresh user fields if available (Sync with models)
    limit = float(current_user.credit_limit or 0)
    available = float(current_user.available_credit or 0)
    
    if limit == 0:
        limit = float(
            getattr(latest_risk, "recommended_limit", None)
            or (getattr(latest_limit, "new_limit", None) if latest_limit else 0)
            or 0
        )
        available = max(limit - outstanding, 0.0) if limit else 0.0

    risk_band = current_user.risk_band or getattr(latest_risk, "risk_band", None) or "pending_assessment"
    assessment_status = "active" if limit > 0 else "pending_assessment"
    next_review_date = current_user.next_review_date.date().isoformat() if current_user.next_review_date else None
    if not next_review_date:
        if latest_risk:
            next_review_date = (latest_risk.created_at + timedelta(days=90)).date().isoformat()
        elif latest_limit:
            next_review_date = (latest_limit.created_at + timedelta(days=90)).date().isoformat()

    return {
        "credit_limit": limit,
        "available_credit": available,
        "risk_band": risk_band,
        "assessment_status": assessment_status,
        "next_review_date": next_review_date,
    }


# ============================================================================
# TASK-23: Credit History Endpoint
# ============================================================================

@router.get("/history")
async def credit_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Endpoint for customers to view their credit limit history"""
    from sqlalchemy import func
    
    offset = (page - 1) * limit
    rows = (await db.execute(
        select(CreditLimitHistory)
        .where(CreditLimitHistory.user_id == current_user.id)
        .order_by(CreditLimitHistory.created_at.desc())
        .offset(offset).limit(limit)
    )).scalars().all()
    
    total = await db.scalar(
        select(func.count()).select_from(
            select(CreditLimitHistory).where(CreditLimitHistory.user_id == current_user.id).subquery()
        )
    )
    
    return {
        "items": [
            {
                "id": r.id,
                "previous_limit": float(r.previous_limit or 0),
                "new_limit": float(r.new_limit or 0),
                "available_before": float(r.available_before or 0),
                "available_after": float(r.available_after or 0),
                "reason": r.reason,
                "changed_by": r.changed_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": int(total or 0)},
    }
