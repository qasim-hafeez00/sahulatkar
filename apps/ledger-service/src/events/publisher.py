from __future__ import annotations

from typing import Any
from sk_shared.events import (
    build_event_envelope,
    event_channel,
    EVENT_LEDGER_JOURNAL_POSTED,
    EVENT_LEDGER_INSTALLMENTS_OVERDUE,
    EVENT_LEDGER_LATE_FEE_APPLIED,
    EVENT_LEDGER_RECONCILIATION_MATCHED,
    EVENT_LEDGER_CHARITY_DISBURSED,
    EVENT_LEDGER_SHARIAH_VIOLATION_DETECTED,
    EVENT_LEDGER_PAYMENT_COLLECTION_TRIGGERED,
    EVENT_BILLING_INSTALLMENT_OVERDUE,
)
from sk_shared.redis_client import RedisClient

class EventPublisher:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis

    async def publish_journal_posted(self, entry_id: int, entry_number: str, payload: dict[str, Any]) -> None:
        await self._publish(EVENT_LEDGER_JOURNAL_POSTED, {
            "entry_id": entry_id,
            "entry_number": entry_number,
            **payload
        })

    async def publish_installments_overdue(self, installment_ids: list[int], as_of: str) -> None:
        await self._publish(EVENT_LEDGER_INSTALLMENTS_OVERDUE, {
            "installment_ids": installment_ids,
            "as_of": as_of
        })

    async def publish_late_fee_applied(self, installment_id: int, amount: float) -> None:
        await self._publish(EVENT_LEDGER_LATE_FEE_APPLIED, {
            "installment_id": installment_id,
            "amount": amount
        })

    async def publish_reconciliation_matched(self, settlement_id: int, matched_ids: list[int]) -> None:
        await self._publish(EVENT_LEDGER_RECONCILIATION_MATCHED, {
            "settlement_id": settlement_id,
            "matched_ids": matched_ids
        })

    async def publish_charity_disbursed(self, disbursement_amount: float, reference: str) -> None:
        await self._publish(EVENT_LEDGER_CHARITY_DISBURSED, {
            "amount": disbursement_amount,
            "reference": reference
        })

    async def publish_shariah_violation(self, reason: str, details: dict[str, Any]) -> None:
        await self._publish(EVENT_LEDGER_SHARIAH_VIOLATION_DETECTED, {
            "reason": reason,
            **details
        })

    async def publish_payment_collection_triggered(
        self,
        *,
        installment_id: int,
        loan_id: int,
        user_id: int,
        amount: float,
        due_date: str,
    ) -> None:
        """LS-CRIT-04: Signal Payment Orchestrator to trigger auto-collection."""
        await self._publish(EVENT_LEDGER_PAYMENT_COLLECTION_TRIGGERED, {
            "installment_id": installment_id,
            "loan_id": loan_id,
            "user_id": user_id,
            "amount": amount,
            "due_date": due_date,
        })

    async def publish_billing_installment_overdue(
        self,
        *,
        installment_id: int,
        order_id: int,
        user_id: int,
        amount: float,
        days_overdue: int,
    ) -> None:
        """NS-BL-05: Per-installment overdue event so notification service can alert the customer."""
        await self._publish(EVENT_BILLING_INSTALLMENT_OVERDUE, {
            "installment_id": installment_id,
            "order_id": order_id,
            "user_id": user_id,
            "amount": amount,
            "days_overdue": days_overdue,
        })

    async def _publish(self, event_name: str, payload: dict[str, Any]) -> None:
        envelope = build_event_envelope(
            event=event_name,
            source_service="ledger-service",
            payload=payload
        )
        await self.redis.publish(event_channel(event_name), envelope.to_json())
