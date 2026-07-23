"""Application-level audit trail for credit-engine's admin-facing actions (limit overrides,
blacklist writes, explanation views) — writes into the same `gateway_audit_events` table
apps/gateway's admin surfaces already use (one shared Postgres, `module` distinguishes the
origin), mirroring apps/gateway/src/core/audit.py's pattern. Before this, none of
credit-engine's admin actions left any forensic record — "did anyone view this customer's
credit explanation, and when" was unanswerable.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.audit import AuditTrail

_logger = logging.getLogger(__name__)

_DLQ_KEY = "sk:audit:dlq"


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
    severity: str = "info",
) -> None:
    ip_address = request.client.host if request and request.client else None
    request_id = getattr(request.state, "request_id", None) if request else None

    try:
        audit_record = AuditTrail(
            admin_user_id=admin_user_id,
            customer_user_id=customer_user_id,
            module=module,
            action=action,
            target_id=target_id,
            changes=changes or {},
            ip_address=ip_address,
            request_id=request_id,
            severity=severity,
        )
        db.add(audit_record)
        # Caller must call db.commit() explicitly.
    except Exception as exc:
        _logger.error("Failed to record audit event module=%s action=%s: %s", module, action, exc, exc_info=True)
        # Write to Redis dead-letter queue for async retry so compliance records are never silently dropped.
        try:
            from sk_shared.redis_client import get_redis_client
            from src.config import settings
            _dlq_payload = json.dumps({
                "admin_user_id": admin_user_id,
                "customer_user_id": customer_user_id,
                "module": module,
                "action": action,
                "target_id": target_id,
                "changes": changes or {},
                "ip_address": ip_address,
                "request_id": request_id,
                "severity": severity,
                "error": str(exc),
            })
            _redis = get_redis_client(settings.redis_url)
            if hasattr(_redis, "redis"):
                await _redis.redis.rpush(_DLQ_KEY, _dlq_payload)
            await _redis.close()
        except Exception as dlq_exc:
            _logger.critical(
                "AUDIT_DLQ_WRITE_FAILED module=%s action=%s dlq_error=%s",
                module, action, dlq_exc,
            )
