from src.extractors.playwright_agent import PlaywrightExtractionAgent


def test_detect_platform_rules():
    agent = PlaywrightExtractionAgent()
    assert agent._detect_platform("https://www.daraz.pk/products/demo-1.html") == "DARAZ"
    assert agent._detect_platform("https://www.amazon.com/dp/B012345678") == "AMAZON"
    assert agent._detect_platform("https://demo.myshopify.com/products/t-shirt") == "SHOPIFY"
    assert agent._detect_platform("https://example.com/item/1") == "CUSTOM"


def test_validation_rejects_bad_payloads():
    agent = PlaywrightExtractionAgent()

    assert agent._is_valid({"title": "", "price": 100, "availability": "in_stock"}) is False
    assert agent._is_valid({"title": "OK", "price": 0, "availability": "in_stock"}) is False
    assert agent._is_valid({"title": "Valid title", "price": 100, "availability": "invalid"}) is False


def test_validation_accepts_valid_payload():
    agent = PlaywrightExtractionAgent()
    assert agent._is_valid({"title": "Valid product", "price": "1200.00", "availability": "in_stock"}) is True
