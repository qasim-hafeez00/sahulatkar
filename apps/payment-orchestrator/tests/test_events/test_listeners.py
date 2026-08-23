"""
Tests for src/events/listeners.py's ledger.payment_collection_triggered
handler — the LS-CRIT-04 / PO-EP-06 wiring fix.

Before this fix, Ledger Service's BillingSweepWorker published this event on
every overdue installment, and the /internal/installments/{id}/auto-collect
endpoint it needed to reach already existed — but nothing subscribed to the
channel, so overdue installments were never actually auto-charged.
"""
import respx
from httpx import Response

import pytest

from src.events.listeners import handle_payment_collection_triggered


@pytest.mark.asyncio
async def test_handle_payment_collection_triggered_calls_auto_collect_endpoint(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "SELF_BASE_URL", "http://testserver")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-internal-token")

    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("http://testserver/api/v1/internal/installments/501/auto-collect").mock(
            return_value=Response(200, json={"status": "success", "txn_id": 1, "installment_id": 501})
        )
        await handle_payment_collection_triggered(
            {"installment_id": 501, "loan_id": 9, "user_id": 42, "amount": 1500.0, "due_date": "2026-07-01"}
        )

    assert route.called
    sent_request = route.calls[0].request
    assert sent_request.headers["x-internal-token"] == "test-internal-token"


@pytest.mark.asyncio
async def test_handle_payment_collection_triggered_missing_installment_id_is_noop(caplog):
    """A malformed event must not raise or attempt any HTTP call."""
    with respx.mock(assert_all_called=False) as mock:
        await handle_payment_collection_triggered({"loan_id": 9})
        assert len(mock.calls) == 0


@pytest.mark.asyncio
async def test_handle_payment_collection_triggered_logs_but_does_not_raise_on_failure(monkeypatch):
    """A failed auto-collect call (e.g. gateway declined) must be logged, not
    raised — this runs inside the Redis pub/sub listener loop, and one bad
    event must not kill the whole listener."""
    from src.config import settings

    monkeypatch.setattr(settings, "SELF_BASE_URL", "http://testserver")
    monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "test-internal-token")

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://testserver/api/v1/internal/installments/502/auto-collect").mock(
            return_value=Response(500, json={"detail": "GATEWAY_DECLINED"})
        )
        # Must not raise.
        await handle_payment_collection_triggered({"installment_id": 502})
