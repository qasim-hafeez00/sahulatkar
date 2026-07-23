from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from sk_shared.models.product import Product

from src.config import settings
from src.services.audit_service import AuditService
from src.services.checkout.vcn_verifier import VcnVerifier
from src.services.extraction_waterfall import ExtractionResult, ExtractionWaterfallService
from src.services.product_extraction_service import ProductExtractionService, build_upo


@pytest.mark.asyncio
async def test_build_upo_uses_enriched_product_fields():
    product = Product(
        uuid=uuid4(),
        name="Enriched Product",
        url="https://example.com/product/enriched",
        canonical_url="https://example.com/product/enriched",
        platform="CUSTOM",
        currency="PKR",
        cost_price=Decimal("1200.00"),
        sale_price=Decimal("1200.00"),
        stock_status="in_stock",
        in_stock=True,
        extraction_method="json_ld",
        extraction_confidence=Decimal("0.850"),
        brand="Acme",
        description="A detailed description.",
        ships_to_pakistan=False,
        primary_image_s3="products/1/main.jpg",
        secondary_images=["products/1/secondary.jpg"],
        variants=[{"option_name": "Size", "selected_value": "M", "available": True}],
    )

    upo = build_upo(product)

    assert upo.meta.brand == "Acme"
    assert upo.meta.description == "A detailed description."
    assert upo.meta.images == ["products/1/main.jpg", "products/1/secondary.jpg"]
    assert upo.shipping is not None
    assert upo.shipping.ships_to_pakistan is False
    assert len(upo.variants) == 1
    assert upo.variants[0].option_name == "Size"
    assert upo.variants[0].options[0].value == "M"


@pytest.mark.asyncio
async def test_circuit_breaker_failure_count_resets_on_success(redis_mock):
    service = ExtractionWaterfallService(redis_mock)

    for _ in range(3):
        await service._trip_circuit_breaker("tier1")

    await service._reset_circuit_breaker("tier1")
    assert await redis_mock.get("sk:cb:failures:tier1") is None


@pytest.mark.asyncio
async def test_audit_service_writes_audit_trails():
    """AuditService.log_action must persist via the AuditTrail ORM model
    (gateway_audit_events table) — a prior raw-SQL version targeted a
    nonexistent "audit_trail" table name, so every call silently failed."""
    from sk_shared.models.audit import AuditTrail

    fake_db = MagicMock()
    fake_db.add = MagicMock()

    service = AuditService(fake_db)
    await service.log_action(
        admin_user_id=7,
        action="prohibit_product",
        target_id=99,
        changes={"reason": "policy"},
        ip_address="203.0.113.5",
    )

    fake_db.add.assert_called_once()
    added = fake_db.add.call_args.args[0]
    assert isinstance(added, AuditTrail)
    assert added.admin_user_id == 7
    assert added.action == "prohibit_product"
    assert added.target_id == 99
    assert added.changes == {"reason": "policy"}
    assert added.ip_address == "203.0.113.5"


@pytest.mark.asyncio
async def test_vcn_verifier_timeout_comes_from_settings(monkeypatch, redis_mock):
    monkeypatch.setattr(settings, "VCN_VERIFICATION_TIMEOUT_SECONDS", 4)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(redis_mock, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(redis_mock, "delete", AsyncMock())

    verifier = VcnVerifier(redis_mock)
    result = await verifier.verify_charge(123)

    assert result is False
    assert asyncio.sleep.await_count == 2


@pytest.mark.asyncio
async def test_image_cache_called_after_extraction(db_session, redis_mock, monkeypatch):
    from src.services.extraction_waterfall import ExtractionWaterfallService

    async def fake_extract(self, canonical_url: str, platform: str):
        return ExtractionResult(
            status="completed",
            method="json_ld",
            confidence=Decimal("0.900"),
            title="Cached Image Product",
            price=Decimal("4500.00"),
            availability="in_stock",
            image_url="https://example.com/images/main.jpg",
            images=["https://example.com/images/main.jpg", "https://example.com/images/secondary.jpg"],
            ships_to_pakistan=True,
        )

    cache_mock = AsyncMock(return_value="products/product-uuid/main.jpg")
    monkeypatch.setattr(ExtractionWaterfallService, "extract", fake_extract)
    monkeypatch.setattr("src.services.s3_service.S3Service.cache_product_image", cache_mock)

    service = ProductExtractionService(db_session, redis_mock)
    response = await service.extract_or_enqueue(
        raw_url="https://example.com/products/cached-image",
        user_id=101,
        client_ip="203.0.113.10",
    )

    assert response.status == "completed"
    product = await db_session.scalar(
        select(Product).where(Product.canonical_url == "https://example.com/products/cached-image")
    )
    assert product is not None
    assert product.primary_image_s3 == "products/product-uuid/main.jpg"
    assert product.secondary_images == ["https://example.com/images/secondary.jpg"]
    assert cache_mock.await_count == 1
