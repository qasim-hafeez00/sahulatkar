from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, field_validator


EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED = "payment.down_payment_confirmed"
EVENT_PAYMENT_INSTALLMENT_PAID = "payment.installment_paid"
EVENT_PAYMENT_CONFIRMED = "payment.confirmed"
EVENT_PAYMENT_SESSION_EXPIRED = "payment.session_expired"
EVENT_PAYMENT_REFUND_INITIATED = "payment.refund_initiated"
EVENT_PAYMENT_REFUND_SETTLED = "payment.refund_settled"
EVENT_PAYMENT_REFUND_FAILED = "payment.refund_failed"
EVENT_PAYMENT_ADJUSTMENT_REQUESTED = "payment.adjustment_requested"
EVENT_VCN_CHARGED = "vcn.charged"
EVENT_LEDGER_DOWN_PAYMENT_POSTED = "ledger.down_payment_posted"
EVENT_LEDGER_PURCHASE_POSTED = "ledger.purchase_posted"
EVENT_LEDGER_INSTALLMENT_PAID = "ledger.installment_paid"
EVENT_LEDGER_LATE_FEE_RECORDED = "ledger.late_fee_recorded"
EVENT_VCN_ISSUED = "vcn.issued"
EVENT_ORDER_PURCHASE_CONFIRMED = "order.purchase_confirmed"
EVENT_ORDER_CANCELLED = "order.cancelled"
EVENT_LOAN_CREATED = "loan.created"
EVENT_DELIVERY_STATUS_CHANGED = "delivery.status_changed"
EVENT_DELIVERY_CONFIRMED = "delivery.confirmed"
EVENT_DELIVERY_RETURNED = "delivery.returned"

# Ledger Outbound Events
EVENT_LEDGER_JOURNAL_POSTED = "ledger.journal_posted"
EVENT_LEDGER_INSTALLMENTS_OVERDUE = "ledger.installments_overdue"
EVENT_LEDGER_LATE_FEE_APPLIED = "ledger.late_fee_applied"
EVENT_LEDGER_RECONCILIATION_MATCHED = "ledger.reconciliation_matched"
EVENT_LEDGER_CHARITY_DISBURSED = "ledger.charity_disbursed"
EVENT_LEDGER_SHARIAH_VIOLATION_DETECTED = "ledger.shariah_violation_detected"
# LS-CRIT-04: Triggers Payment Orchestrator to attempt collection for an overdue installment.
EVENT_LEDGER_PAYMENT_COLLECTION_TRIGGERED = "ledger.payment_collection_triggered"
# NS-BL-05: Per-installment overdue alert published by billing sweep for notification delivery.
EVENT_BILLING_INSTALLMENT_OVERDUE = "billing.installment_overdue"

# Credit Engine events — see apps/credit-engine/src/services/pipeline.py.
EVENT_CREDIT_EVALUATION_REQUESTED = "credit.evaluation_requested"
EVENT_CREDIT_APPROVED = "credit.approved"
EVENT_CREDIT_REJECTED = "credit.rejected"
EVENT_CREDIT_MANUAL_REVIEW_REQUIRED = "credit.manual_review_required"
EVENT_CREDIT_LIMIT_CHANGED = "credit.limit_changed"
EVENT_FRAUD_DETECTED = "fraud.detected"
EVENT_CUSTOMER_RISK_UPDATED = "customer.risk_updated"

# All known event names — used by EventEnvelopeSchema for publish-side validation.
_KNOWN_EVENTS: frozenset[str] = frozenset({
    EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED,
    EVENT_PAYMENT_INSTALLMENT_PAID,
    EVENT_PAYMENT_CONFIRMED,
    EVENT_PAYMENT_SESSION_EXPIRED,
    EVENT_PAYMENT_REFUND_INITIATED,
    EVENT_PAYMENT_REFUND_SETTLED,
    EVENT_PAYMENT_REFUND_FAILED,
    EVENT_PAYMENT_ADJUSTMENT_REQUESTED,
    EVENT_VCN_ISSUED,
    EVENT_VCN_CHARGED,
    EVENT_LEDGER_DOWN_PAYMENT_POSTED,
    EVENT_LEDGER_PURCHASE_POSTED,
    EVENT_LEDGER_INSTALLMENT_PAID,
    EVENT_LEDGER_LATE_FEE_RECORDED,
    EVENT_ORDER_PURCHASE_CONFIRMED,
    EVENT_ORDER_CANCELLED,
    EVENT_LOAN_CREATED,
    EVENT_DELIVERY_STATUS_CHANGED,
    EVENT_DELIVERY_CONFIRMED,
    EVENT_DELIVERY_RETURNED,
    EVENT_LEDGER_JOURNAL_POSTED,
    EVENT_LEDGER_INSTALLMENTS_OVERDUE,
    EVENT_LEDGER_LATE_FEE_APPLIED,
    EVENT_LEDGER_RECONCILIATION_MATCHED,
    EVENT_LEDGER_CHARITY_DISBURSED,
    EVENT_LEDGER_SHARIAH_VIOLATION_DETECTED,
    EVENT_LEDGER_PAYMENT_COLLECTION_TRIGGERED,
    EVENT_BILLING_INSTALLMENT_OVERDUE,
    EVENT_CREDIT_EVALUATION_REQUESTED,
    EVENT_CREDIT_APPROVED,
    EVENT_CREDIT_REJECTED,
    EVENT_CREDIT_MANUAL_REVIEW_REQUIRED,
    EVENT_CREDIT_LIMIT_CHANGED,
    EVENT_FRAUD_DETECTED,
    EVENT_CUSTOMER_RISK_UPDATED,
})


class EventEnvelopeSchema(BaseModel):
    """Pydantic model for publish-side event envelope validation.

    Prevents malformed or unknown events from entering the bus.
    """

    event: str
    event_id: str
    timestamp: str
    source_service: str
    correlation_id: str
    payload: dict[str, Any]

    @field_validator("event")
    @classmethod
    def event_must_be_known(cls, v: str) -> str:
        if v not in _KNOWN_EVENTS:
            raise ValueError(
                f"Unknown event '{v}'. Register it in sk_shared.events._KNOWN_EVENTS before publishing."
            )
        return v

    @field_validator("source_service")
    @classmethod
    def source_service_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_service must not be empty")
        return v

    @field_validator("payload")
    @classmethod
    def payload_must_be_dict(cls, v: Any) -> dict:
        if not isinstance(v, dict):
            raise ValueError("payload must be a JSON object (dict)")
        return v


@dataclass(slots=True)
class EventEnvelope:
    event: str
    event_id: str
    timestamp: str
    source_service: str
    correlation_id: str
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def build_event_envelope(
    *,
    event: str,
    source_service: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> EventEnvelope:
    envelope = EventEnvelope(
        event=event,
        event_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        source_service=source_service,
        correlation_id=correlation_id or str(uuid4()),
        payload=payload,
    )
    # Validate on the publish side so malformed envelopes are caught at the source.
    EventEnvelopeSchema(**asdict(envelope))
    return envelope


def event_channel(event_name: str) -> str:
    return f"sk:events:{event_name}"