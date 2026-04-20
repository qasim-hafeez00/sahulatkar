import pytest
import asyncio
from decimal import Decimal
from src.services.extraction_waterfall import ExtractionWaterfallService, ExtractionResult

@pytest.mark.asyncio
async def test_extraction_circuit_breaker_trips(monkeypatch, redis_mock):
    service = ExtractionWaterfallService(redis_mock)
    
    # Mock tier1 and tier2a to fail
    async def fake_fail(*args, **kwargs):
        return None
        
    # We use a platform that includes tier1 and tier2a (e.g. AMAZON)
    monkeypatch.setattr(service, "_tier1_rye", fake_fail)
    monkeypatch.setattr(service, "_tier2a_violet", fake_fail)
    
    # Fail 4 times
    for _ in range(4):
        # This will fail tier1 and tier2a, incrementing both circuit breakers
        await service.extract("https://example.com/p", "AMAZON")
        
    # Should NOT be blocked yet
    assert await redis_mock.get("sk:cb:blocked:tier1") is None
    assert await redis_mock.get("sk:cb:blocked:tier2a") is None
    
    # 5th failure
    await service.extract("https://example.com/p", "AMAZON")
    
    # Should BE blocked now
    assert await redis_mock.get("sk:cb:blocked:tier1") == "1"
    assert await redis_mock.get("sk:cb:blocked:tier2a") == "1"

@pytest.mark.asyncio
async def test_extraction_circuit_breaker_blocks_calls(monkeypatch, redis_mock):
    service = ExtractionWaterfallService(redis_mock)
    
    # Manually block tier1 in Redis
    await redis_mock.set("sk:cb:blocked:tier1", "1", ttl=60)
    
    status = {"tier1_called": False, "tier2a_called": False}
    
    async def fake_tier1(*args, **kwargs):
        status["tier1_called"] = True
        return None
        
    async def fake_tier2a(*args, **kwargs):
        status["tier2a_called"] = True
        return ExtractionResult(
            status="completed", 
            method="violet_api", 
            confidence=Decimal("0.900"), 
            title="Circuit Test Product", 
            price=Decimal("100.00"),
            availability="in_stock"
        )

    monkeypatch.setattr(service, "_tier1_rye", fake_tier1)
    monkeypatch.setattr(service, "_tier2a_violet", fake_tier2a)
    monkeypatch.setattr(service, "_validate_extraction", lambda x: x) # Skip validation for simplicity
    
    result = await service.extract("https://example.com/p", "AMAZON")
    
    # Tier 1 should be skipped because it's blocked
    assert status["tier1_called"] is False
    # Tier 2a should be called and return the result
    assert status["tier2a_called"] is True
    assert result.status == "completed"
    assert result.method == "violet_api"
