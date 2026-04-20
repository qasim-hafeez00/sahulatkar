import time
from prometheus_client import Counter, Histogram
from prometheus_client import Gauge
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)
EXTRACTION_LATENCY = Histogram(
    "extraction_duration_seconds",
    "Product extraction duration by tier",
    ["tier", "status"],
    buckets=[0.1, 0.5, 1.0, 5.0, 15.0, 30.0, 60.0],
)
CHECKOUT_JOB_DURATION = Histogram(
    "checkout_job_duration_seconds",
    "Checkout job duration by status",
    ["status"],
    buckets=[1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0],
)
CHECKOUT_STEP_DURATION = Histogram(
    "checkout_step_duration_seconds",
    "Checkout duration by step",
    ["step"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
CHECKOUT_JOBS_TOTAL = Counter(
    "checkout_jobs_total",
    "Total checkout jobs by status",
    ["status"],
)
SCRAPING_JOBS_TOTAL = Counter(
    "scraping_jobs_total",
    "Total scraping jobs by platform and status",
    ["platform", "status"],
)
RYE_API_CALLS_TOTAL = Counter(
    "rye_api_calls_total",
    "Rye API call outcomes",
    ["status"],
)
VLM_CALLS_TOTAL = Counter(
    "vlm_calls_total",
    "VLM self-healing calls",
    ["reason"],
)
CAPTCHA_SOLVE_TOTAL = Counter(
    "captcha_solve_total",
    "CAPTCHA solving outcomes",
    ["provider", "result"],
)
PROHIBITED_ITEMS_DETECTED_TOTAL = Counter(
    "prohibited_items_detected_total",
    "Prohibited item detections",
    ["category"],
)
EXTRACT_RATE_LIMIT_HITS = Counter(
    "extract_rate_limit_hits_total",
    "Total extraction rate limit hits",
    ["tier"],
)
VCN_VERIFICATION_TIMEOUT = Counter(
    "vcn_verification_timeout_total",
    "Total VCN verification timeouts",
    ["vcn_id"],
)
CHECKOUT_QUEUE_DIRECTION_VIOLATION = Counter(
    "checkout_queue_direction_violation_total",
    "Total checkout queue direction violations",
)
DLQ_DEPTH = Gauge(
    "dlq_depth",
    "Current DLQ depth by queue",
    ["queue"],
)

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        endpoint = request.url.path
        REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
        return response
