from enum import Enum
from typing import Dict, Set


class PaymentStatus(str, Enum):
    INITIATED = "initiated"
    PENDING = "pending"            # Async gateways: awaiting webhook (SafePay redirect, Raast IBFT)
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    EXPIRED = "expired"
    FAILED = "failed"
    ABANDONED = "abandoned"
    REFUND_INITIATED = "refund_initiated"
    REFUNDED = "refunded"
    REFUND_FAILED = "refund_failed"
    VOID = "void"


class PaymentWorkflowError(Exception):
    pass


# Legal state transitions matrix
_TRANSITIONS: Dict[PaymentStatus, Set[PaymentStatus]] = {
    PaymentStatus.INITIATED: {
        PaymentStatus.PENDING,       # Async gateway redirect issued (SafePay, Raast)
        PaymentStatus.AUTHORIZED,
        PaymentStatus.CAPTURED,      # Sync gateways (JazzCash direct charge)
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.PENDING: {
        PaymentStatus.CAPTURED,      # Webhook confirms payment cleared
        PaymentStatus.FAILED,        # Webhook signals failure
        PaymentStatus.EXPIRED,       # Session TTL exceeded before webhook arrived
    },
    PaymentStatus.AUTHORIZED: {
        PaymentStatus.CAPTURED,
        PaymentStatus.VOID,
        PaymentStatus.FAILED,
    },
    PaymentStatus.FAILED: {
        PaymentStatus.INITIATED,     # Retry (admin force-retry)
        PaymentStatus.ABANDONED,
    },
    PaymentStatus.CAPTURED: {
        PaymentStatus.REFUND_INITIATED,
        PaymentStatus.VOID,          # Allow voiding if not yet settled in bank
    },
    PaymentStatus.REFUND_INITIATED: {
        PaymentStatus.REFUNDED,
        PaymentStatus.REFUND_FAILED,
    },
}


def validate_transition(from_status: PaymentStatus, to_status: PaymentStatus) -> None:
    if from_status == to_status:
        return

    allowed = _TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise PaymentWorkflowError(
            f"Illegal payment state transition: {from_status.value} -> {to_status.value}"
        )
