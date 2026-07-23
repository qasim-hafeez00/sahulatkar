"""Internal service-to-service HTTP client.

Gateway owns the `users` table and already exposes an authenticated callback
(`POST /internal/users/{user_id}/credit-result`, see
`apps/gateway/src/api/v1/internal.py::credit_result_callback`) built exactly for
credit-engine to push decisions back to — it was wired up on the gateway side but never
called from here, which is why `users.credit_limit` / `available_credit` / `risk_band`
go stale the moment credit-engine makes a decision. This client closes that gap using the
same `X-Internal-Token` shared-secret convention gateway's `_require_internal` already
enforces, mirroring the `InternalServiceClient` pattern in
`apps/gateway/src/core/http_client.py` and `apps/product-service/src/core/http_client.py`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import uuid4

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def start() -> None:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.GATEWAY_URL,
            timeout=settings.INTERNAL_HTTP_TIMEOUT_SECONDS,
        )


async def stop() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _signed_headers(request_id: Optional[str] = None) -> dict[str, str]:
    return {
        "X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN,
        "X-Request-ID": request_id or str(uuid4()),
        "Content-Type": "application/json",
    }


async def push_credit_result(
    *,
    user_id: int,
    risk_band: str,
    credit_limit: float,
    available_credit: float,
    recommended_limit: float,
    decision: str,
    assessment_id: Optional[int] = None,
    next_review_days: int = 90,
) -> bool:
    """Push a decision to Gateway's users table. Best-effort: a Gateway outage must not
    block the credit decision itself (the CreditApplication/RiskAssessment rows already
    persisted in credit-engine's own DB are the system of record) — but it does mean
    `users.credit_limit` is stale until the next successful decision or a manual resync,
    so failures are logged loudly rather than swallowed silently.
    """
    if _client is None:
        logger.error("push_credit_result called before http_client.start(); skipping sync to gateway")
        return False

    payload = {
        "risk_band": risk_band,
        "credit_limit": credit_limit,
        "available_credit": available_credit,
        "recommended_limit": recommended_limit,
        "decision": decision,
        "assessment_id": assessment_id,
        "next_review_days": next_review_days,
    }

    # A transient network blip or a gateway restart shouldn't be the difference between
    # users.credit_limit staying in sync or going stale until the next decision — retry a
    # bounded number of times with backoff before giving up. A 4xx (payload/auth problem) is
    # not transient, so it's not worth retrying.
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = await _client.post(
                f"/internal/users/{user_id}/credit-result",
                json=payload,
                headers=_signed_headers(),
            )
            if response.status_code >= 500 and attempt < max_attempts:
                logger.warning(
                    "credit_result_push_retrying user_id=%s status=%s attempt=%s",
                    user_id, response.status_code, attempt,
                )
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            if response.status_code >= 400:
                logger.error(
                    "credit_result_push_failed user_id=%s status=%s body=%s",
                    user_id, response.status_code, response.text[:500],
                )
                return False
            return True
        except httpx.HTTPError:
            if attempt < max_attempts:
                logger.warning("credit_result_push_retrying user_id=%s attempt=%s", user_id, attempt, exc_info=True)
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            logger.exception("credit_result_push_error user_id=%s", user_id)
            return False
    return False
