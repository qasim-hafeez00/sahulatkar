"""
INF-GAP-04: Gateway's outbound internal calls (product-service, credit-engine,
payment-orchestrator, notification-service) must forward the inbound request's
X-Request-ID by default, not mint a disconnected one, so an order is
traceable end-to-end across the pipeline.
"""
import pytest

from sk_shared.correlation import set_correlation_id
from src.core.http_client import InternalServiceClient

pytestmark = pytest.mark.asyncio


async def test_signed_headers_defaults_to_inbound_correlation_id():
    set_correlation_id("req-gw-001")
    headers = InternalServiceClient.signed_headers()
    assert headers["X-Request-ID"] == "req-gw-001"


async def test_signed_headers_explicit_request_id_overrides_context():
    set_correlation_id("req-gw-context")
    headers = InternalServiceClient.signed_headers(request_id="req-gw-explicit")
    assert headers["X-Request-ID"] == "req-gw-explicit"


async def test_notification_admin_headers_defaults_to_inbound_correlation_id(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "INTERNAL_API_KEY", "test-internal-key")
    set_correlation_id("req-gw-admin")
    headers = InternalServiceClient.notification_admin_headers(admin_id=1, role="ops", permissions=["view"])
    assert headers["X-Request-ID"] == "req-gw-admin"
