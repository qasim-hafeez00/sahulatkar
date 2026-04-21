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
        """
        try:
            await self.db.execute(
                text(
                    """
                    INSERT INTO audit_trail (
                        module,
                        action,
                        target_id,
                        admin_user_id,
                        ip_address,
                        changes,
                        created_at
                    )
                    VALUES (
                        :module,
                        :action,
                        :target_id,
                        :admin_user_id,
                        :ip_address,
                        :changes,
                        :created_at
                    )
                    """
                ),
                {
                    "module": module,
                    "action": action,
                    "target_id": target_id,
                    "admin_user_id": admin_user_id,
                    "ip_address": ip_address,
                    "changes": changes if changes else {},
                    "created_at": datetime.now(timezone.utc),
                },
            )
            # We don't commit here; caller should commit as part of the transaction.
        except Exception as exc:
            logger.error("Failed to log audit event: %s", exc)
            # We don't raise; audit failures shouldn't break business logic in this context,
            # but in strict production we might want to.
            return
