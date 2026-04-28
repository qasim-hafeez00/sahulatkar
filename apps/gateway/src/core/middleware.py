import uuid
import time
from urllib.parse import urlparse
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sk_shared.correlation import set_correlation_id
from src.config import settings
from .logging import logger

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        # Populate ContextVar so any outbound httpx/aiohttp call in this coroutine
        # can forward the correlation ID via get_propagation_headers().
        set_correlation_id(request_id)

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)
        return response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # SEC-02: IP allowlisting for admin login endpoint.
        if request.url.path.endswith("/admin/auth/login") and request.method == "POST":
            allowlist_raw = settings.ADMIN_IP_ALLOWLIST.strip()
            if allowlist_raw:
                allowed = {ip.strip() for ip in allowlist_raw.split(",") if ip.strip()}
                client_ip = request.client.host if request.client else ""
                if client_ip not in allowed:
                    logger.warning("Admin login blocked for IP %s — not in allowlist", client_ip)
                    return JSONResponse(status_code=403, content={"detail": "ADMIN_LOGIN_IP_BLOCKED"})

        # SEC-07: Defense-in-depth origin check for admin state-changing calls.
        if (
            settings.ENVIRONMENT in {"production", "staging"}
            and request.url.path.startswith("/api/v1/admin")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not request.url.path.startswith("/api/v1/admin/auth/login")
        ):
            allowed_host = urlparse(settings.ADMIN_ALLOWED_ORIGIN).netloc.lower()
            origin = request.headers.get("Origin", "")
            referer = request.headers.get("Referer", "")
            origin_host = urlparse(origin).netloc.lower() if origin else ""
            referer_host = urlparse(referer).netloc.lower() if referer else ""
            if origin_host != allowed_host and referer_host != allowed_host:
                return JSONResponse(status_code=403, content={"detail": "ADMIN_ORIGIN_FORBIDDEN"})

        response = await call_next(request)
        
        # Don't apply restrictive headers to documentation routes
        if request.url.path in ["/docs", "/openapi.json", "/redoc"]:
            return response

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
