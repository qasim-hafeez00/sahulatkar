from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_endpoint_reports_listener_state(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "ledger-service"
    assert "listener_running" in payload
    assert "watchdog_running" in payload


@pytest.mark.asyncio
async def test_readiness_reports_listener_health(client, seed_ledger_accounts):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert "listeners" in payload
    assert set(payload["listeners"].keys()) == {"ledger_event_listener", "ledger_event_watchdog"}


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_text(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
