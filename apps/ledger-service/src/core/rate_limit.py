from fastapi import Request

from sk_shared.rate_limit import rate_limit_dependency


def _admin_write_identity(request: Request) -> str:
    """Rate-limit key identity: prefer the authenticated admin actor id
    (set on request.state by upstream auth), falling back to client IP for
    unauthenticated/system callers -- same fallback ledger-service's
    bespoke limiter used before migrating onto sk_shared.rate_limit."""
    actor_id = getattr(request.state, "actor_id", None)
    if actor_id:
        return str(actor_id)
    return request.client.host if request.client else "unknown"


# P3-05: Rate limiting on all admin write endpoints: 10 requests/minute per
# admin actor ID (or IP if no actor id is present).
#
# Migrated onto sk_shared.rate_limit.SlidingWindowRateLimiter (via the
# rate_limit_dependency factory) instead of ledger-service's own fixed-window
# INCR/EXPIRE counter -- same limit/window/key-prefix/identity behavior, but a
# true sliding window (no fixed-window boundary where ~2x the limit can slip
# through) and one fewer bespoke rate limiter implementation to maintain
# across the fleet. fail_open is left at its default (False), matching the
# old implementation's behavior of not swallowing Redis errors.
rate_limit_admin_writes = rate_limit_dependency(
    limit=10,
    window_seconds=60,
    key_prefix="rate_limit:admin_write",
    identity_fn=_admin_write_identity,
    detail="Rate limit exceeded. Maximum 10 admin write requests per minute allowed.",
)
