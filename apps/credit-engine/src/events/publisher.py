from __future__ import annotations

import logging
from typing import Any

from sk_shared.events import (
    build_event_envelope,
    event_channel,
    EVENT_CREDIT_EVALUATION_REQUESTED,
    EVENT_CREDIT_APPROVED,
    EVENT_CREDIT_REJECTED,
    EVENT_CREDIT_MANUAL_REVIEW_REQUIRED,
    EVENT_CREDIT_LIMIT_CHANGED,
    EVENT_FRAUD_DETECTED,
    EVENT_CUSTOMER_RISK_UPDATED,
)
from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)

_DLQ_KEY = "sk:credit:events:dlq"


class CreditEventPublisher:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    async def publish_evaluation_requested(self, *, user_id: str, order_amount: float, product_category: str) -> None:
        await self._publish(EVENT_CREDIT_EVALUATION_REQUESTED, {
            "user_id": user_id,
            "order_amount": order_amount,
            "product_category": product_category,
        })

    async def publish_approved(self, *, user_id: str, assessment_id: str | None, risk_band: str, approved_limit: float, down_payment_pct: float) -> None:
        await self._publish(EVENT_CREDIT_APPROVED, {
            "user_id": user_id,
            "assessment_id": assessment_id,
            "risk_band": risk_band,
            "approved_limit": approved_limit,
            "down_payment_pct": down_payment_pct,
        })

    async def publish_rejected(self, *, user_id: str, assessment_id: str | None, reason: str, flags: list[str]) -> None:
        await self._publish(EVENT_CREDIT_REJECTED, {
            "user_id": user_id,
            "assessment_id": assessment_id,
            "reason": reason,
            "flags": flags,
        })

    async def publish_manual_review_required(self, *, user_id: str, assessment_id: str | None, reason: str) -> None:
        await self._publish(EVENT_CREDIT_MANUAL_REVIEW_REQUIRED, {
            "user_id": user_id,
            "assessment_id": assessment_id,
            "reason": reason,
        })

    async def publish_limit_changed(self, *, user_id: str, old_limit: float, new_limit: float, reason_code: str, changed_by_type: str) -> None:
        await self._publish(EVENT_CREDIT_LIMIT_CHANGED, {
            "user_id": user_id,
            "old_limit": old_limit,
            "new_limit": new_limit,
            "reason_code": reason_code,
            "changed_by_type": changed_by_type,
        })

    async def publish_fraud_detected(self, *, user_id: str, alert_type: str, severity: str, flags: list[str]) -> None:
        await self._publish(EVENT_FRAUD_DETECTED, {
            "user_id": user_id,
            "alert_type": alert_type,
            "severity": severity,
            "flags": flags,
        })

    async def publish_risk_updated(self, *, user_id: str, risk_band: str, score: float | None) -> None:
        await self._publish(EVENT_CUSTOMER_RISK_UPDATED, {
            "user_id": user_id,
            "risk_band": risk_band,
            "score": score,
        })

    async def _publish(self, event_name: str, payload: dict[str, Any]) -> None:
        envelope = build_event_envelope(
            event=event_name,
            source_service="credit-engine",
            payload=payload,
        )
        message = envelope.to_json()
        try:
            await self.redis.publish(event_channel(event_name), message)
        except Exception:
            # Pub/sub is fire-and-forget by nature — a decision already committed to Postgres
            # must never fail because Redis hiccuped. This is a best-effort dead-letter (same
            # Redis instance, so it doesn't help if Redis itself is fully down) that at least
            # makes a dropped credit.approved/fraud.detected event replayable instead of
            # silently lost, which is what happened before. A DB-backed outbox (write in the
            # same transaction as the decision, relay separately) would be the fully durable
            # fix, but that's new infrastructure beyond this pass's scope.
            logger.error("credit_event_publish_failed event=%s", event_name, exc_info=True)
            try:
                await self.redis.rpush(_DLQ_KEY, message)
            except Exception:
                logger.critical("credit_event_dlq_write_failed event=%s", event_name, exc_info=True)
