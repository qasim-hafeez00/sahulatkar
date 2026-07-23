"""Generic manager-approval workflow — Module 2 (credit-limit) and Module 4 (restructuring) share this."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.admin import AdminApprovalRequest
from sk_shared.models.auth import AdminUser
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/approval-requests", tags=["Admin Approvals"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _serialize(row: AdminApprovalRequest) -> dict:
    return {
        "id": row.id,
        "uuid": str(row.uuid),
        "request_type": row.request_type,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "requested_by": row.requested_by,
        "payload": row.payload,
        "reason": row.reason,
        "status": row.status,
        "decided_by": row.decided_by,
        "decided_at": _iso(row.decided_at),
        "decision_note": row.decision_note,
        "created_at": _iso(row.created_at),
    }


@router.get("")
async def list_approval_requests(
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    query = select(AdminApprovalRequest)
    if status_filter:
        query = query.where(AdminApprovalRequest.status == status_filter)
    if request_type:
        query = query.where(AdminApprovalRequest.request_type == request_type)

    rows = (
        await db.execute(query.order_by(AdminApprovalRequest.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()

    return {
        "items": [_serialize(r) for r in rows],
        "pagination": {"page": page, "limit": limit},
    }


@router.get("/{request_id}")
async def get_approval_request(
    request_id: int,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.scalar(select(AdminApprovalRequest).where(AdminApprovalRequest.id == request_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APPROVAL_REQUEST_NOT_FOUND")
    return _serialize(row)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    decision_note: Optional[str] = Field(default=None, max_length=500)


@router.post("/{request_id}/decision")
async def decide_approval_request(
    request_id: int,
    payload: ApprovalDecisionRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_users")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.scalar(select(AdminApprovalRequest).where(AdminApprovalRequest.id == request_id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="APPROVAL_REQUEST_NOT_FOUND")
    if row.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="APPROVAL_REQUEST_ALREADY_DECIDED")
    if row.requested_by == current_admin.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CANNOT_APPROVE_OWN_REQUEST")

    from datetime import datetime, timezone

    row.status = payload.decision
    row.decided_by = current_admin.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = payload.decision_note

    applied = False
    if payload.decision == "approved" and row.request_type == "credit_limit_increase":
        from sk_shared.models.auth import User as UserModel

        user_obj = await db.scalar(select(UserModel).where(UserModel.id == row.entity_id))
        if user_obj:
            new_limit = row.payload.get("new_limit")
            if new_limit is not None:
                user_obj.credit_limit = new_limit
                user_obj.available_credit = new_limit
                applied = True

    await record_audit_event(
        db=db,
        request=request,
        admin_user_id=current_admin.id,
        module="admin_approvals",
        action=f"decision_{payload.decision}",
        target_id=request_id,
        changes={"request_type": row.request_type, "applied": applied},
    )
    await db.commit()
    return {"id": row.id, "status": row.status, "applied": applied}
