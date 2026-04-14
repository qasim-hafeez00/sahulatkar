from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from playwright.async_api import async_playwright
from playwright_stealth import stealth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        if not execution or execution.status in {"succeeded", "failed", "hitl_escalated"}:
            return

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
            browser_args = []
            if settings.BRIGHTDATA_PROXY_URL:
                browser_args.append(f"--proxy-server={settings.BRIGHTDATA_PROXY_URL}")

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

    async def _human_type(self, page, selector: str, text: str):
        await page.wait_for_selector(selector)
        await page.focus(selector)
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.05, 0.15))

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