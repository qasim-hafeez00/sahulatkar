from __future__ import annotations

import contextvars
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_http_client: httpx.AsyncClient | None = None


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id or "")


def get_request_id() -> str:
    return _request_id_ctx.get()


async def init_http_client() -> None:
    global _http_client
    if _http_client is not None:
        return

    timeout = httpx.Timeout(
        connect=settings.INTERNAL_HTTP_CONNECT_TIMEOUT_SECONDS,
        read=settings.INTERNAL_HTTP_READ_TIMEOUT_SECONDS,
        write=settings.INTERNAL_HTTP_READ_TIMEOUT_SECONDS,
        pool=settings.INTERNAL_HTTP_READ_TIMEOUT_SECONDS,
    )
    _http_client = httpx.AsyncClient(timeout=timeout)


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    if _http_client is None:
        raise RuntimeError("Internal HTTP client is not initialized")

    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("X-Internal-Service-Token", settings.INTERNAL_SERVICE_TOKEN)

    request_id = get_request_id()
    if request_id:
        headers.setdefault("X-Request-ID", request_id)

    response = await _http_client.request(method, url, headers=headers, **kwargs)

    if response.status_code >= 500:
        body = (response.text or "")[:500]
        logger.error(
            "internal_http_5xx method=%s url=%s status_code=%s body=%s",
            method,
            url,
            response.status_code,
            body,
        )

    return response
