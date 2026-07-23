from __future__ import annotations

from fastapi import Request

from sk_shared.rate_limit import rate_limit_dependency
from sk_shared.security import decode_access_token
from src.config import settings


def _identity(request: Request) -> str:
    """Per-user rate limiting where possible (decodes the bearer token without re-validating
    it — an expired/invalid token still gets its own bucket, no worse than falling back to
    IP), falling back to per-IP for callers with no/garbled Authorization header."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        try:
            payload = decode_access_token(auth_header[7:], settings.JWT_PUBLIC_KEY)
        except Exception:
            payload = {}
        identity = payload.get("user_id") or payload.get("admin_id")
        if identity:
            return f"user:{identity}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


# Applied to the hot decision-making endpoints (/credit/check, /credit/evaluate,
# /credit/apply, /credit/prequalify, /credit/recalculate) — the ones that run the full engine
# pipeline and, for apply, write a CreditApplication row. Read-only endpoints
# (status/history/score/explain) are left unlimited.
credit_decision_rate_limit = rate_limit_dependency(
    limit=30,
    window_seconds=60,
    key_prefix="sk:ratelimit:credit:decision",
    identity_fn=_identity,
)

# Admin-facing endpoints (override/adjust limit, blacklist writes) run DB writes and push a
# sync to gateway — previously unthrottled beyond the admin-auth check itself, so a
# compromised admin token had no ceiling on how fast it could hammer them.
credit_admin_rate_limit = rate_limit_dependency(
    limit=60,
    window_seconds=60,
    key_prefix="sk:ratelimit:credit:admin",
    identity_fn=_identity,
)
