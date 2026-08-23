"""
Prometheus metrics registry for payment orchestrator.
All counters and histograms are module-level singletons.
"""
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

# ── Payment Counters ────────────────────────────────────────────────────────

DOWN_PAYMENT_TOTAL = Counter(
    "payment_down_payment_total",
    "Total down payment initiations",
    ["gateway", "status"],  # status: initiated | success | failed
)

INSTALLMENT_PAYMENT_TOTAL = Counter(
    "payment_installment_total",
    "Total installment payment attempts",
    ["gateway", "status"],
)

REFUND_TOTAL = Counter(
    "payment_refund_total",
    "Total refund initiations",
    ["gateway", "status"],
)

# ── VCN Counters ────────────────────────────────────────────────────────────

VCN_ISSUED_TOTAL = Counter(
    "vcn_issued_total",
    "Total VCNs issued",
    ["issuer"],  # issuer: stripe | lithic
)

VCN_VOID_TOTAL = Counter(
    "vcn_void_total",
    "Total VCNs voided",
    ["reason"],  # reason: manual_void | order_cancelled | expired
)

VCN_CHARGE_CONFIRMED_TOTAL = Counter(
    "vcn_charge_confirmed_total",
    "Total VCN charges confirmed",
)

# ── Webhook Counters ────────────────────────────────────────────────────────

WEBHOOK_RECEIVED_TOTAL = Counter(
    "payment_webhook_received_total",
    "Total gateway webhooks received",
    ["gateway", "outcome"],  # outcome: processed | duplicate | invalid_sig | ignored
)

# ── Gateway Health ────────────────────────────────────────────────────────

GATEWAY_FAILURE_TOTAL = Counter(
    "payment_gateway_failure_total",
    "Total payment gateway failures",
    ["gateway"],
)

# ── Reconciliation ────────────────────────────────────────────────────────

RECONCILIATION_MATCHED_TOTAL = Counter(
    "payment_reconciliation_matched_total",
    "Total transactions matched in reconciliation",
    ["gateway"],
)

RECONCILIATION_DISCREPANCY_TOTAL = Counter(
    "payment_reconciliation_discrepancy_total",
    "Total discrepancies found during reconciliation",
    ["gateway", "type"],  # label 'type' values: amount_mismatch | missing_in_gateway | missing_internally
)

# ── Latency Histograms ──────────────────────────────────────────────────────

REQUEST_LATENCY = Histogram(
    "payment_request_latency_seconds",
    "HTTP request latency for payment orchestrator endpoints",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

VCN_ISSUE_LATENCY = Histogram(
    "vcn_issue_latency_seconds",
    "Latency for VCN issuance end-to-end",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ── Orchestration State Machine ──────────────────────────────────────────────

WORKFLOW_STATE_TRANSITIONS_TOTAL = Counter(
    "payment_workflow_state_transitions_total",
    "Total payment workflow state transitions",
    ["from_status", "to_status", "gateway"],
)

# ── Outbox Publisher ─────────────────────────────────────────────────────────


def _get_or_create_gauge(name: str, documentation: str) -> Gauge:
    """Return an existing Gauge if already registered, otherwise register it."""
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Gauge(name, documentation)


OUTBOX_QUEUE_DEPTH = _get_or_create_gauge(
    "payment_outbox_queue_depth",
    "Number of pending/failed outbox events awaiting publication",
)

VCN_AUTH_REJECTED_TOTAL = Counter(
    "vcn_auth_rejected_total",
    "Total rejected Stripe issuing authorization requests",
)

EVENT_LISTENER_UP = _get_or_create_gauge(
    "payment_event_listener_up",
    "Redis order-cancel listener connectivity status (1=up, 0=down)",
)

