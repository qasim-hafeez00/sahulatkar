from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI

instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
    inprogress_name="inprogress",
    inprogress_labels=True,
)

def setup_metrics(app: FastAPI):
    instrumentator.instrument(app).expose(app, endpoint="/metrics")


# Business metrics — the auto-instrumented defaults above only cover generic HTTP
# request/latency/status-by-route, which tells a risk team nothing about approve/reject mix,
# fraud pressure, or manual-review load. These are what an actual alert ("fraud rate spiked",
# "manual review queue is backing up") would page on.
credit_decisions_total = Counter(
    "credit_decisions_total",
    "Credit decisions by outcome and risk band",
    ["outcome", "risk_band"],
)
credit_manual_review_total = Counter(
    "credit_manual_review_total",
    "Decisions flagged for manual review",
)
credit_fraud_score = Histogram(
    "credit_fraud_score",
    "Composite fraud risk score per evaluation (0-100+)",
    buckets=(0, 10, 20, 40, 60, 80, 100, 150),
)
credit_fraud_alerts_total = Counter(
    "credit_fraud_alerts_total",
    "Fraud alerts raised, by severity",
    ["severity"],
)
