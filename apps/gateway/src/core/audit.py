from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.audit import AuditTrail


async def record_audit_event(
    db: AsyncSession,
    request: Request | None,
    *,
    admin_user_id: int | None = None,
    customer_user_id: int | None = None,
    module: str,
    action: str,
    target_id: int | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    ip_address = request.client.host if request and request.client else None
    request_id = getattr(request.state, "request_id", None) if request else None

    audit_record = AuditTrail(
        admin_user_id=admin_user_id,
        customer_user_id=customer_user_id,
        module=module,
        action=action,
        target_id=target_id,
        changes=changes or {},
        ip_address=ip_address,
        request_id=request_id,
    )
    db.add(audit_record)
    # Caller must run db.commit() explicitly
