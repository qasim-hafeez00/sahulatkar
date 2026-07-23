import logging
import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
        return response

def setup_cors(app, allow_origins: list[str]):
    """Configure CORS with an explicit origin allowlist.

    No wildcard default: allow_credentials=True combined with
    allow_origins=["*"] lets any site read authenticated responses, so
    callers must pass the specific origins their environment permits.
    """
    if not allow_origins:
        raise ValueError("setup_cors requires at least one explicit allow_origins entry")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
