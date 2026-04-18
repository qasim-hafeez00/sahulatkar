from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from sk_shared.models.auth import User
from src.core.dependencies import get_current_user

router = APIRouter(prefix="/credit", tags=["credit"])


@router.get("/status")
async def credit_status(current_user: User = Depends(get_current_user)) -> dict:
    limit = float(getattr(current_user, "credit_limit", 0) or 0)
    available = float(getattr(current_user, "available_credit", 0) or 0)
    
    # If limit is 0, the user might be pending initial assessment
    assessment_status = "active"
    if limit <= 0:
        assessment_status = "pending_assessment"

    return {
        "credit_limit": limit,
        "available_credit": available,
        "risk_band": getattr(current_user, "risk_band", "unavailable"),
        "assessment_status": assessment_status,
        "next_review_date": getattr(current_user, "next_review_date", None) or datetime.now(timezone.utc).date().isoformat(),
    }
