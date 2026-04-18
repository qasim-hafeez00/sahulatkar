from __future__ import annotations

import logging
import time
from uuid import uuid4

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter(
    "ledger_http_requests_total",
    "Total HTTP requests handled by ledger-service",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "ledger_http_request_duration_seconds",
    "HTTP request duration for ledger-service",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        REQUEST_COUNT.labels(request.method, request.url.path, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration_ms / 1000)

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request processed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
