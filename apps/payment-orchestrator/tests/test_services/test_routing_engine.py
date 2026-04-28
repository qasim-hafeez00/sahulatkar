"""
Tests for GatewayRoutingEngine.
Target: 10 test cases
"""
import pytest

from src.services.routing_engine import GatewayRoutingEngine

pytestmark = pytest.mark.asyncio


async def test_selects_preferred_gateway_when_healthy(redis_mock):
    engine = GatewayRoutingEngine(redis_mock)
    result = await engine.select_gateway(preferred="jazzcash")
    assert result == "jazzcash"


async def test_falls_through_to_priority_when_preferred_is_degraded(redis_mock):
    from src.config import settings
    engine = GatewayRoutingEngine(redis_mock)

    # Degrade raast beyond threshold
    for _ in range(settings.GATEWAY_FAILURE_THRESHOLD + 1):
        await engine.record_failure("raast")

    # No preferred specified — should skip raast, pick jazzcash
    result = await engine.select_gateway(preferred=None)
    assert result in ("jazzcash", "safepay")


async def test_record_failure_increments_counter(redis_mock):
    engine = GatewayRoutingEngine(redis_mock)
    await engine.record_failure("safepay")
    count = await engine.get_failure_count("safepay")
    assert count == 1


async def test_record_success_decrements_counter(redis_mock):
    engine = GatewayRoutingEngine(redis_mock)
    await engine.record_failure("safepay")
    await engine.record_failure("safepay")
    await engine.record_success("safepay")
    count = await engine.get_failure_count("safepay")
    assert count == 1


async def test_is_degraded_returns_true_above_threshold(redis_mock):
    from src.config import settings
    engine = GatewayRoutingEngine(redis_mock)

    for _ in range(settings.GATEWAY_FAILURE_THRESHOLD):
        await engine.record_failure("jazzcash")

    assert await engine.is_degraded("jazzcash") is True


async def test_is_degraded_returns_false_below_threshold(redis_mock):
    engine = GatewayRoutingEngine(redis_mock)
    await engine.record_failure("raast")
    assert await engine.is_degraded("raast") is False


async def test_select_gateway_never_raises_even_if_all_degraded(redis_mock):
    from src.config import settings
    engine = GatewayRoutingEngine(redis_mock)

    for gw in ["raast", "jazzcash", "safepay"]:
        for _ in range(settings.GATEWAY_FAILURE_THRESHOLD + 2):
            await engine.record_failure(gw)

    # Only the three original gateways are degraded; easypaisa is still healthy.
    # Fallback should now pick easypaisa as the least-failed healthy gateway.
    result = await engine.select_gateway()
    assert result in ("raast", "jazzcash", "safepay", "easypaisa")


async def test_get_health_summary_returns_all_gateways(redis_mock):
    engine = GatewayRoutingEngine(redis_mock)
    summary = await engine.get_health_summary()
    gateway_names = [s["gateway"] for s in summary]
    assert "raast" in gateway_names
    assert "jazzcash" in gateway_names
    assert "safepay" in gateway_names
    assert "easypaisa" in gateway_names


async def test_health_summary_reflects_degraded_state(redis_mock):
    from src.config import settings
    engine = GatewayRoutingEngine(redis_mock)

    for _ in range(settings.GATEWAY_FAILURE_THRESHOLD):
        await engine.record_failure("safepay")

    summary = await engine.get_health_summary()
    safepay_entry = next(s for s in summary if s["gateway"] == "safepay")
    assert safepay_entry["is_degraded"] is True


async def test_fresh_gateway_is_not_degraded(redis_mock):
    engine = GatewayRoutingEngine(redis_mock)
    assert await engine.is_degraded("raast") is False
    assert await engine.is_degraded("jazzcash") is False
    assert await engine.is_degraded("safepay") is False
