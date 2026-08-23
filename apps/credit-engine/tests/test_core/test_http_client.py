"""
INF-GAP-04: credit-engine's callback to Gateway (push_credit_result) must
carry the X-Request-ID of the inbound request that triggered the credit
decision, not an unrelated freshly-minted UUID, so an order can be traced
end-to-end through Gateway -> Credit Engine -> Gateway.
"""
import pytest

from sk_shared.correlation import set_correlation_id
from src.core.http_client import _signed_headers

pytestmark = pytest.mark.asyncio


async def test_signed_headers_defaults_to_inbound_correlation_id():
    set_correlation_id("req-abc-123")
    headers = _signed_headers()
    assert headers["X-Request-ID"] == "req-abc-123"


async def test_signed_headers_explicit_request_id_overrides_context():
    set_correlation_id("req-context-id")
    headers = _signed_headers(request_id="req-explicit-id")
    assert headers["X-Request-ID"] == "req-explicit-id"


async def test_signed_headers_generates_fallback_when_no_context_set():
    # No RequestIdMiddleware ran in this test (no live request) — get_correlation_id()
    # must still return a non-empty, usable ID rather than raising or returning "".
    set_correlation_id("")
    headers = _signed_headers()
    assert headers["X-Request-ID"]
