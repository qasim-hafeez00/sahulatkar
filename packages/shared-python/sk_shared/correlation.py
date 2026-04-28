"""Correlation ID (X-Request-ID) propagation helpers.

Gateway middleware generates a request-scoped X-Request-ID.  Any downstream
HTTP call made from a service should forward this header so that a single user
request can be traced across the full pipeline.

Usage (httpx):

    async with httpx.AsyncClient(headers=get_propagation_headers(request)) as client:
        resp = await client.post(...)

Usage (plain dict):

    headers = get_propagation_headers(request)
    await some_internal_client.call(headers=headers)
"""
from __future__ import annotations

import contextvars
import uuid
from typing import Mapping

from starlette.requests import Request

# Thread/coroutine-local store — populated by middleware for every inbound request.
_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)

HEADER_NAME = "X-Request-ID"


def set_correlation_id(request_id: str) -> None:
    """Called by RequestIDMiddleware once per inbound request."""
    _correlation_id_var.set(request_id)


def get_correlation_id() -> str:
    """Return the current correlation ID, generating one if not set."""
    value = _correlation_id_var.get()
    if not value:
        value = str(uuid.uuid4())
        _correlation_id_var.set(value)
    return value


def get_propagation_headers(request: Request | None = None) -> dict[str, str]:
    """Return a dict with X-Request-ID suitable for forwarding to downstream services.

    Prefers the value already stored in request.state (set by Gateway middleware),
    falling back to the ContextVar, then generating a fresh UUID.
    """
    if request is not None and hasattr(request.state, "request_id"):
        return {HEADER_NAME: request.state.request_id}
    return {HEADER_NAME: get_correlation_id()}
