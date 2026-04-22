from prometheus_client import Counter, Histogram, Gauge, REGISTRY

# Ensure we don't duplicate metrics if module is reloaded
def _get_or_create_metric(metric_cls, name, documentation, labelnames=()):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return metric_cls(name, documentation, labelnames=labelnames)

JOURNAL_ENTRIES_TOTAL = _get_or_create_metric(
    Counter,
    "ledger_journal_entries_total",
    "Total journal entries created",
    labelnames=("entry_type",)
)

LATE_FEES_APPLIED_TOTAL = _get_or_create_metric(
    Counter,
    "ledger_late_fees_applied_total",
    "Total number of late fees applied"
)

CHARITY_DISBURSEMENTS_TOTAL_PKR = _get_or_create_metric(
    Counter,
    "ledger_charity_disbursements_total_pkr",
    "Total charity disbursed in PKR"
)

BILLING_SWEEP_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "ledger_billing_sweep_duration_seconds",
    "Duration of billing sweep execution"
)

BILLING_SWEEP_OVERDUE_DETECTED_TOTAL = _get_or_create_metric(
    Counter,
    "ledger_billing_sweep_overdue_detected_total",
    "Total number of overdue installments detected"
)

RECONCILIATION_DISCREPANCY_TOTAL_PKR = _get_or_create_metric(
    Gauge,
    "ledger_reconciliation_discrepancy_total_pkr",
    "Total discrepancy amount in latest reconciliation"
)

SHARIAH_COMPLIANCE_RATIO = _get_or_create_metric(
    Gauge,
    "ledger_shariah_compliance_ratio",
    "Ratio of disbursed to allocated charity (1.0 = compliant)"
)
SHARIAH_COMPLIANCE_RATIO.set(1.0) # Default healthy state

DLQ_MESSAGES_TOTAL = _get_or_create_metric(
    Counter,
    "ledger_dlq_messages_total",
    "Total dead letter queue messages",
    labelnames=("event_name",)
)

PERIOD_STATUS = _get_or_create_metric(
    Gauge,
    "ledger_period_status",
    "Status of accounting period (0=open, 1=soft_closed, 2=closed)",
    labelnames=("period_key",)
)
