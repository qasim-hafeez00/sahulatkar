from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


EVENT_PAYMENT_DOWN_PAYMENT_CONFIRMED = "payment.down_payment_confirmed"
EVENT_PAYMENT_INSTALLMENT_PAID = "payment.installment_paid"
EVENT_LEDGER_DOWN_PAYMENT_POSTED = "ledger.down_payment_posted"
EVENT_LEDGER_PURCHASE_POSTED = "ledger.purchase_posted"
EVENT_LEDGER_INSTALLMENT_PAID = "ledger.installment_paid"
EVENT_LEDGER_LATE_FEE_RECORDED = "ledger.late_fee_recorded"
EVENT_VCN_ISSUED = "vcn.issued"
EVENT_ORDER_PURCHASE_CONFIRMED = "order.purchase_confirmed"
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
    return EventEnvelope(
        event=event,
        event_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        source_service=source_service,
        correlation_id=correlation_id or str(uuid4()),
        payload=payload,
    )


def event_channel(event_name: str) -> str:
    return f"sk:events:{event_name}"