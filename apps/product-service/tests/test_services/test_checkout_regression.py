from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sk_shared.redis_client import RedisClient


async def _seed_order_vcn(db_session):
    """Minimal seed: create an Order + VirtualCard for checkout tests."""
    from sk_shared.models.order import Order
    from sk_shared.models.payment import VirtualCard
    from sk_shared.models.product import Product
    from decimal import Decimal

    product = Product(
        name="Test Product",
        url="https://example.com/product",
        canonical_url="https://example.com/product",
        platform="CUSTOM",
        currency="PKR",
        cost_price=Decimal("5000.00"),
        sale_price=Decimal("5000.00"),
        stock_status="in_stock",
        in_stock=True,
        extraction_method="json_ld",
        extraction_confidence=Decimal("0.9"),
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        user_id=1,
        product_id=product.id,
        status="pending",
        total_amount=5000.00,
    )
    db_session.add(order)
    await db_session.flush()

    # VirtualCard has many required (non-nullable) columns.
    now = datetime.now(timezone.utc)
    vcn = VirtualCard(
        order_id=order.id,
        user_id=1,
        issuer="STRIPE",
        issuer_card_id=f"vcn_test_{order.id}",
        masked_number="4111********1111",
        card_expiry=date(now.year + 1, 1, 1),
        authorized_amount=5000.00,
        loaded_amount=5000.00,
        issued_at=now,
        expires_at=now + timedelta(days=30),
        status="active",
    )
    db_session.add(vcn)
    await db_session.flush()
    return order, vcn


@pytest.mark.asyncio
async def test_bug01_order_is_passed_to_playwright_checkout(db_session, redis_mock):
    """BUG-01 regression: order must be in scope inside run_checkout."""
    from src.services.checkout import CheckoutAgentService
    from sk_shared.models.checkout import PurchaseExecution

    order, vcn = await _seed_order_vcn(db_session)
    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
        attempt_number=0,
    )
    db_session.add(execution)
    await db_session.commit()
    await db_session.refresh(execution)

    captured: dict = {}

    async def fake_run_checkout(product, order, pan, cvv, attempt_number, execution_uuid):
        captured["order"] = order
        return {
            "merchant_order_id": "SK-TEST-001",
            "merchant_order_url": "https://example.com/confirm",
            "receipt_screenshot": None,
        }

    service = CheckoutAgentService(db_session, redis_mock)
    
    # Patch the class methods
    with patch("src.services.checkout.form_filler.CheckoutFormFiller.run_checkout", side_effect=fake_run_checkout):
        with patch("src.services.checkout.vcn_verifier.VcnVerifier.verify_charge", AsyncMock(return_value=True)):
            await service.process_job({"execution_id": str(execution.uuid)})

    assert "order" in captured, (
        "BUG-01 not fixed: run_checkout was not called with 'order' parameter."
    )
    assert captured["order"].id == order.id


@pytest.mark.asyncio
async def test_bug03_screenshot_captured_before_browser_close_and_uploaded(db_session, redis_mock):
    """BUG-03 regression: receipt screenshot must be uploaded to S3."""
    from src.services.checkout import CheckoutAgentService
    from src.services.s3_service import S3Service
    from sk_shared.models.checkout import PurchaseExecution

    order, vcn = await _seed_order_vcn(db_session)
    execution = PurchaseExecution(
        order_id=order.id,
        vcn_id=vcn.id,
        status="queued",
        step_reached="queued",
        queued_at=datetime.now(timezone.utc),
        attempt_number=0,
    )
    db_session.add(execution)
    await db_session.commit()
    await db_session.refresh(execution)

    FAKE_SCREENSHOT = b"\xff\xd8\xff\xe0fake_jpeg_bytes"
    s3_uploads: list[dict] = []

    async def fake_run_checkout(product, order, pan, cvv, attempt_number, execution_uuid):
        return {
            "merchant_order_id": "SK-TEST-002",
            "merchant_order_url": "https://example.com/confirm",
            "receipt_screenshot": FAKE_SCREENSHOT,
        }

    async def fake_s3_upload(self, data: bytes, key: str, content_type: str = "image/jpeg"):
        s3_uploads.append({"data": data, "key": key})
        return key

    service = CheckoutAgentService(db_session, redis_mock)
    
    with patch("src.services.checkout.form_filler.CheckoutFormFiller.run_checkout", side_effect=fake_run_checkout):
        with patch("src.services.checkout.vcn_verifier.VcnVerifier.verify_charge", AsyncMock(return_value=True)):
            with patch.object(S3Service, "upload_bytes", fake_s3_upload):
                await service.process_job({"execution_id": str(execution.uuid)})

    assert len(s3_uploads) == 1
    assert s3_uploads[0]["data"] == FAKE_SCREENSHOT
    assert "success_receipt" in s3_uploads[0]["key"]

    await db_session.refresh(execution)
    assert execution.receipt_screenshot_s3 is not None
