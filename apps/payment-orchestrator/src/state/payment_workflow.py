from enum import Enum
from typing import Dict, Set


class PaymentStatus(str, Enum):
    INITIATED = "initiated"
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
        PaymentStatus.AUTHORIZED,
        PaymentStatus.CAPTURED,  # For sync gateways
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.AUTHORIZED: {
        PaymentStatus.CAPTURED,
        PaymentStatus.VOID,
        PaymentStatus.FAILED,
    },
    PaymentStatus.FAILED: {
        PaymentStatus.INITIATED,  # Retry
        PaymentStatus.ABANDONED,
    },
    PaymentStatus.CAPTURED: {
        PaymentStatus.REFUND_INITIATED,
        PaymentStatus.VOID, # Allow voiding if not yet settled in bank
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
