import asyncio

import pytest


@pytest.mark.asyncio
async def test_health_live(client):
    res = await client.get("/health/live")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_summary(client):
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "product-service"
    assert body["status"] in {"ok", "degraded"}


@pytest.mark.asyncio
async def test_health_ready_not_ready_when_db_or_listener_unhealthy(client):
    app = client._transport.app
    app.state.db_healthy = False
    app.state.listener_task = None

    res = await client.get("/health/ready")
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "not_ready"
    assert body["db"] == "down"


@pytest.mark.asyncio
async def test_health_ready_ok_when_deps_healthy(client):
    app = client._transport.app
    app.state.db_healthy = True
    app.state.listener_task = asyncio.create_task(asyncio.sleep(5))

    try:
        res = await client.get("/health/ready")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ready"
        assert body["db"] == "ok"
        assert body["redis"] == "ok"
    finally:
        app.state.listener_task.cancel()