from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_action(
        self,
        admin_user_id: Optional[int],
        action: str,
        target_id: Optional[int],
        changes: Optional[dict[str, Any]] = None,
        module: str = "product-service",
        ip_address: Optional[str] = None,
    ) -> None:
        """Log an administrative or lifecycle action.
        
        Using raw SQL to insert into audit_trail if dedicated table doesn't exist in model yet,
        or we can use the gateway_audit_events table as a proxy if we want to centralize.
        The user asked for 'dedicated', so we use product_audit_events.
        """
        try:
            # We use text() to avoid requiring the model to be registered in Base if it's new
            # or if we are in a migration transition.
            await self.db.execute(
                text(
                    """
                    INSERT INTO product_audit_events (admin_user_id, module, action, target_id, changes, ip_address, created_at)
                    VALUES (:admin_user_id, :module, :action, :target_id, :changes, :ip_address, :created_at)
                    """
                ),
                {
                    "admin_user_id": admin_user_id,
                    "module": module,
                    "action": action,
                    "target_id": target_id,
                    "changes": changes if changes else {},
                    "ip_address": ip_address,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            # We don't commit here; caller should commit as part of the transaction.
        except Exception as exc:
            logger.error("Failed to log audit event: %s", exc)
            # We don't raise; audit failures shouldn't break business logic in this context,
            # but in strict production we might want to.
            return
