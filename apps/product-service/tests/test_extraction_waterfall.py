import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from src.services.extraction_waterfall import ExtractionWaterfallService

@pytest.mark.asyncio
async def test_tier2_jsonld_fallback_returns_completed_result(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'<html><script type="application/ld+json">{"@type": "Product", "name": "Smart Watch", "offers": {"price": "199.99"}}</script></html>'
    
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    
    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: mock_client)
    
    service = ExtractionWaterfallService()
    result = await service.extract("https://merchant.example/product/smart-watch", "CUSTOM")

    assert result.status == "completed"
    assert result.method == "json_ld"
    assert result.title == "Smart Watch"
    assert result.price == Decimal("199.99")

@pytest.mark.asyncio
async def test_tier3_execution_returns_completed_or_failed(monkeypatch):
    # Mock the PlaywrightExtractionAgent to avoid real browser launch
    mock_agent = MagicMock()
    mock_agent.extract = AsyncMock(return_value={"title": "Smart Watch", "price": 199.99})
    
    monkeypatch.setattr("src.extractors.playwright_agent.PlaywrightExtractionAgent", lambda: mock_agent)
    monkeypatch.setattr("src.services.extraction_waterfall.settings.FEATURE_GROQ_ENABLED", True)

    service = ExtractionWaterfallService()
    result = await service.run_tier3("https://merchant.example/product/smart-watch", "CUSTOM")

    assert result.status == "completed"
    assert result.method == "playwright_llm"
    assert result.title == "Smart Watch"
