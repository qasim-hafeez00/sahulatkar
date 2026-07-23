from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.audit import AuditTrail


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

        Uses the shared AuditTrail ORM model (gateway_audit_events table) —
        a prior raw-SQL version targeted a nonexistent "audit_trail" table
        name, so every call silently failed and no audit record was ever
        persisted (caught by the blanket except below).
        """
        try:
            self.db.add(
                AuditTrail(
                    admin_user_id=admin_user_id,
                    module=module,
                    action=action,
                    target_id=target_id,
                    changes=changes if changes else {},
                    ip_address=ip_address,
                )
            )
            # We don't commit here; caller should commit as part of the transaction.
        except Exception as exc:
            logger.error("Failed to log audit event: %s", exc)
            # We don't raise; audit failures shouldn't break business logic in this context,
            # but in strict production we might want to.
            return
