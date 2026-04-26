import time
import uuid
from typing import Callable

from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge
from starlette.middleware.base import BaseHTTPMiddleware

# ── HTTP Metrics ──────────────────────────────────────────────────────────────
http_requests_total = Counter(
    "notification_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
http_request_duration_seconds = Histogram(
    "notification_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
)

# ── Dispatch Metrics ──────────────────────────────────────────────────────────
notifications_dispatched_total = Counter(
    "notification_dispatched_total",
    "Total dispatch attempts",
    ["channel", "event_type", "result"],  # result: success | failed | retrying | dlq
)
notification_dispatch_latency_seconds = Histogram(
    "notification_dispatch_latency_seconds",
    "Time to dispatch a notification via a channel",
    ["channel", "provider"],
)

provider_dispatch_errors_total = Counter(
    "notification_provider_errors_total",
    "Total errors encountered per provider",
    ["provider", "error_code"],
)

dispatcher_health = Gauge(
    "dispatcher_health",
    "Health status of dispatchers (1 for UP, 0 for DOWN)",
    ["dispatcher"]
)
notification_queue_depth = Gauge(
    "notification_queue_depth",
    "Current depth of the notification dispatch queue",
)
notification_dlq_depth = Gauge(
    "notification_dlq_depth",
    "Current depth of the notification dead letter queue",
)
notification_retry_queue_depth = Gauge(
    "notification_retry_queue_depth",
    "Current depth of the retry queue",
)

# ── Business Metrics ──────────────────────────────────────────────────────────
otp_sent_total = Counter(
    "notification_otp_sent_total",
    "Total OTPs sent",
    ["purpose"],  # registration | contract_sign | payment_auth
)
otp_rate_limited_total = Counter(
    "notification_otp_rate_limited_total",
    "Total OTP requests rejected by rate limiter",
    ["phone_prefix"],  # Last 3 digits of area code for privacy
)
compliance_notifications_sent_total = Counter(
    "notification_compliance_sent_total",
    "Total compliance (Shariah) notifications sent",
    ["event_type"],
)
dispatcher_health = Gauge(
    "notification_dispatcher_health",
    "Dispatcher health status (1=up, 0=down)",
    ["channel"],
)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Determine endpoint path
        route = request.scope.get("route")
        endpoint = route.path if route else request.url.path
        
        http_requests_total.labels(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        ).inc()
        
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
        
        return response
