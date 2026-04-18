from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.audit import AuditTrail
from fastapi import Request

async def record_audit_event(
    db: AsyncSession, 
    request: Request, 
    user_id: int | None, 
    module: str, 
    action: str, 
    target_id: int | None, 
    changes: dict
):
    ip_address = request.client.host if request.client else None
    request_id = getattr(request.state, "request_id", None)
    
    audit_record = AuditTrail(
        admin_user_id=user_id, # Can be reused for internal user audit mapping
        module=module,
        action=action,
        target_id=target_id,
        changes=changes,
        ip_address=ip_address
    )
    db.add(audit_record)
    await db.commit()
