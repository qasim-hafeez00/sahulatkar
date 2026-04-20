from decimal import Decimal

from src.extractors.html_scraper import HtmlScraper


def test_json_ld_product_extracted():
    scraper = HtmlScraper()
    html = b'<html><script type="application/ld+json">{"@type":"Product","name":"Watch","offers":{"price":"1200","priceCurrency":"PKR","availability":"http://schema.org/InStock"}}</script></html>'
    data = scraper.extract_json_ld(html)
    assert data is not None
    assert data["title"] == "Watch"
    assert data["currency"] == "PKR"


def test_confidence_values_via_result_build():
    scraper = HtmlScraper()
    res = scraper._to_result({"title": "A", "price": "1", "currency": "PKR", "availability": "in_stock", "images": []}, Decimal("0.85"))
    assert res.confidence == Decimal("0.85")
