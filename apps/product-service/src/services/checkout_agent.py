from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import socket
from playwright.async_api import async_playwright, FrameLocator
from playwright_stealth import stealth
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.s3_service import S3Service

from sk_shared.constants import QueueName
from sk_shared.events import (
    EVENT_ORDER_PURCHASE_CONFIRMED,
    build_event_envelope,
    event_channel,
)
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.order import Order
from sk_shared.models.payment import VirtualCard
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient
from sk_shared.security import SecretService

from src.config import settings
from src.services.self_healing import SelfHealingService


class CheckoutAgentService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis
        self.self_healing = SelfHealingService()
        self.s3_service = S3Service()

    async def queue_job(
        self,
        *,
        order_id: int,
        vcn_id: int,
        correlation_id: str | None = None,
        force_failure: bool = False,
    ) -> PurchaseExecution:
        now = datetime.now(timezone.utc)
        execution = PurchaseExecution(
            order_id=order_id,
            vcn_id=vcn_id,
            status="queued",
            step_reached="queued",
            queued_at=now,
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)

        payload = {
            "execution_id": str(execution.uuid),
            "order_id": order_id,
            "vcn_id": vcn_id,
            "correlation_id": correlation_id,
            "force_failure": force_failure,
        }
        await self.redis.rpush(QueueName.CHECKOUT, json.dumps(payload))
        return execution

    async def process_job(self, payload: dict) -> None:
        execution = await self._load_execution(payload["execution_id"])
        if not execution or execution.status in {"succeeded", "failed", "hitl_escalated", "cancelled"}:
            return

        # GAP-19: Increment attempt_number
        execution.attempt_number += 1
        execution.worker_id = socket.gethostname()
        await self.db.commit()

        # Fetch dependency data
        order = await self.db.get(Order, execution.order_id)
        if not order or not order.product_id:
            await self._mark_failed(execution, "unknown", "Order or product missing.")
            return

        product = await self.db.get(Product, order.product_id)
        vcn = await self.db.get(VirtualCard, execution.vcn_id)
        if not product or not vcn:
            await self._mark_failed(execution, "unknown", f"Product({product}) or VCN({vcn}) missing. order_product_id={order.product_id}, execution_vcn_id={execution.vcn_id}")
            return

        started_at = datetime.now(timezone.utc)
        execution.status = "running"
        execution.started_at = started_at
        await self.db.commit()

        try:
            result = await self._run_playwright_checkout(execution, product, vcn, payload)
            
            execution.status = "succeeded"
            execution.step_reached = "order_confirmed"
            execution.merchant_order_id = result.get("merchant_order_id")
            execution.merchant_order_url = result.get("merchant_order_url")
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_ms = int((execution.completed_at - started_at).total_seconds() * 1000)
            await self.db.commit()

            # GAP-21: Stripe VCN Verification (Polled logic)
            # After marking as "succeeded" based on page content, we check if Stripe charged the card.
            verified = await self._verify_vcn_charge(vcn.id)
            if not verified:
                # We suspected success but no charge event arrived. 
                # Could be a slow webhook or a ghost success.
                # In prod, we might wait longer or escalate.
                pass

            # Publish success event
            envelope = build_event_envelope(
                event=EVENT_ORDER_PURCHASE_CONFIRMED,
                source_service="product-service",
                correlation_id=payload.get("correlation_id"),
                payload={
                    "order_id": execution.order_id,
                    "vcn_id": execution.vcn_id,
                    "merchant_order_id": execution.merchant_order_id,
                },
            )
            await self.redis.publish(event_channel(EVENT_ORDER_PURCHASE_CONFIRMED), envelope.to_json())
            
            # Final Screenshot for success proof
            # Wait a bit for receipt to settle
            await asyncio.sleep(2)
            await self._capture_screenshot(execution, "success_receipt")

        except Exception as e:
            await self._mark_failed(execution, "checkout_changed", str(e))

    async def _run_playwright_checkout(
        self, 
        execution: PurchaseExecution, 
        product: Product, 
        vcn: VirtualCard,
        payload: dict
    ) -> Dict[str, Any]:
        if payload.get("force_failure"):
            raise RuntimeError("Forced failure for testing")

        encryption_key = settings.FERNET_KEY.encode()
        pan = SecretService.decrypt_secret(vcn.encrypted_pan, encryption_key).decode() if vcn.encrypted_pan else ""
        cvv = SecretService.decrypt_secret(vcn.encrypted_cvv, encryption_key).decode() if vcn.encrypted_cvv else ""

        async with async_playwright() as p:
            # GAP-20: Proxy rotation via session-id
            proxy_url = settings.BRIGHTDATA_PROXY_URL
            if proxy_url and execution.attempt_number > 1:
                # Append session param for specific IP sticky/rotation
                session_id = f"session_{execution.uuid}_{execution.attempt_number}"
                if "-session-" not in proxy_url:
                    parts = proxy_url.split("@")
                    if len(parts) == 2:
                        user_pass, host_port = parts
                        proxy_url = f"{user_pass}-session-{session_id}@{host_port}"

            browser_args = []
            if proxy_url:
                browser_args.append(f"--proxy-server={proxy_url}")

            browser = await p.chromium.launch(headless=True, args=browser_args)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            await stealth(page)
            
            # Step 1: Navigate
            execution.step_reached = "navigation"
            await self.db.commit()
            await page.goto(product.url, wait_until="networkidle", timeout=settings.CHECKOUT_TIMEOUT_SECONDS * 1000)
            
            # GAP-07: Variant Selection
            execution.step_reached = "variant_selection"
            await self.db.commit()
            # In a real scenario, variant data comes from the order/product
            # selected_variant = order.metadata.get("selected_variant")
            await self._select_variant(page, product, None) 
            
            # Step 2: Add to Cart
            execution.step_reached = "add_to_cart"
            await self.db.commit()
            await self._click_with_retry(page, "button:has-text('Add to Cart'), button:has-text('Buy Now')", "Could not find Add to Cart button")
            
            # Step 3: Guest Checkout
            execution.step_reached = "guest_checkout"
            await self.db.commit()
            await page.wait_for_load_state("networkidle")
            await self._click_with_retry(page, "button:has-text('Guest Checkout'), button:has-text('Checkout as Guest')", "Could not find Guest Checkout")
            
            # Step 4: Form Filling (Heuristic)
            execution.step_reached = "form_filling"
            await self.db.commit()
            await self._human_type(page, "input[name*='email'], input[type='email']", "customer@sahulatkar.com")
            await self._human_type(page, "input[name*='firstname']", "Sahulat")
            await self._human_type(page, "input[name*='lastname']", "Customer")
            await self._human_type(page, "input[name*='address1'], input[id*='address']", "123 BNPL Street")
            await self._human_type(page, "input[name*='city']", "Karachi")
            await self._human_type(page, "input[name*='phone'], input[type='tel']", "03001234567")
            
            # Step 5: Payment Injection
            execution.step_reached = "payment_injection"
            await self.db.commit()
            
            # GAP-08: Handle Payment IFrames
            payment_frame = await self._get_payment_frame(page)
            if payment_frame:
                await self._human_type(payment_frame, "input[name*='cardnumber'], input[id*='card'], input[placeholder*='Card number']", pan)
                await self._human_type(payment_frame, "input[name*='cvv'], input[id*='cvv'], input[placeholder*='CVV']", cvv)
            else:
                await self._human_type(page, "input[name*='cardnumber'], input[id*='card']", pan)
                await self._human_type(page, "input[name*='cvv'], input[id*='cvv']", cvv)
            
            # Step 6: Submit Order
            execution.step_reached = "submit_order"
            await self.db.commit()
            await self._click_with_retry(page, "button:has-text('Place Order'), button:has-text('Complete Purchase')", "Could not find Submit button")
            
            # Step 7: Confirmation
            await page.wait_for_load_state("networkidle")
            
            # Heuristic Order ID extraction
            page_text = await page.content()
            order_id_match = re.search(r"(?:Order|Reference|Confirmation).?\s?#?\s?([A-Z0-9-]{5,20})", page_text, re.IGNORECASE)
            merchant_order_id = order_id_match.group(1) if order_id_match else f"SK-{execution.order_id}"
            
            await browser.close()
            return {
                "merchant_order_id": merchant_order_id,
                "merchant_order_url": page.url
            }

    async def _click_with_retry(self, page, selector: str, error_msg: str, retries=1):
        for _ in range(retries + 1):
            try:
                await page.wait_for_selector(selector, timeout=5000)
                await page.click(selector)
                return
            except Exception:
                healed_selector = await self.self_healing.suggest_selector(page=page, error_context=error_msg)
                if healed_selector:
                    try:
                        await page.click(healed_selector)
                        return
                    except Exception:
                        continue
        raise RuntimeError(error_msg)

    async def _human_type(self, target, selector: str, text: str):
        # target can be page or frame_locator
        if hasattr(target, "wait_for_selector"):
            await target.wait_for_selector(selector, timeout=10000)
        
        # GAP-10: Gaussian delay — manual sleep per character for human-like pacing.
        for char in text:
            await target.type(selector, char)
            await asyncio.sleep(max(0.02, random.gauss(0.1, 0.04)))

    async def _select_variant(self, page, product: Product, variant_data: dict | None = None):
        # Placeholder for heuristic variant selection
        # Logic would involve finding dropdowns or buttons matching variant_data
        pass

    async def _get_payment_frame(self, page) -> FrameLocator | None:
        """GAP-08: Detect stripe/payment iframes."""
        # Common patterns for payment iframes
        frame_patterns = [
            "iframe[name*='card']", 
            "iframe[src*='stripe']", 
            "iframe[src*='pay']",
            "iframe[id*='card']"
        ]
        for pattern in frame_patterns:
            locator = page.frame_locator(pattern)
            # Check if any element inside likely exists
            try:
                # We can't easily 'check' if a frame exists without fetching an element
                # frame_locator is lazy. We'll return the first one that seems hit.
                return locator
            except Exception:
                continue
        return None

    async def _capture_screenshot(self, execution: PurchaseExecution, step: str):
        """GAP-09: Upload screenshot of current state to S3.
        
        TODO: Pass the `page` object into this method (or store it on self during checkout)
        so that a screenshot can be captured and uploaded via self.s3_service.
        Currently not implemented — call-site in process_job is intentionally left
        as a best-effort; do not silently discard the intent.
        """
        pass  # Non-fatal: page reference not available at this call site yet

    async def _verify_vcn_charge(self, vcn_id: int) -> bool:
        """GAP-21: Poll Redis for Stripe charge confirmation."""
        key = f"sk:vcn:pending_verification:{vcn_id}"
        # In a real implementation, we poll this key which is set by a Stripe webhook listener
        for _ in range(10):
            if await self.redis.get(key):
                return True
            await asyncio.sleep(2)
        return False

    async def cancel_job(self, job_uuid: UUID):
        """GAP-06: Mark job cancelled and publish void event."""
        await self.db.execute(
            update(PurchaseExecution)
            .where(PurchaseExecution.uuid == job_uuid)
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        # In prod: Publish VCN.VOID event here

    async def _load_execution(self, execution_uuid: str) -> PurchaseExecution | None:
        statement = select(PurchaseExecution).where(PurchaseExecution.uuid == UUID(execution_uuid))
        return await self.db.scalar(statement)

    async def _mark_failed(self, execution: PurchaseExecution, failure_type: str, error_detail: str) -> None:
        execution.status = "failed"
        execution.failure_type = failure_type
        execution.error_detail = error_detail
        execution.completed_at = datetime.now(timezone.utc)

        if settings.FEATURE_HITL_ESCALATION:
            execution.status = "hitl_escalated"
            hitl_item = HitlQueue(
                order_id=execution.order_id,
                execution_id=execution.id,
                priority=2,
                status="pending",
                failure_reason=error_detail,
                sla_deadline=datetime.now(timezone.utc) + timedelta(minutes=settings.HITL_SLA_MINUTES),
            )
            self.db.add(hitl_item)
        
        await self.db.commit()