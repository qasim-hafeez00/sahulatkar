from __future__ import annotations

import asyncio
import json
import random
import re
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import socket
import httpx
from playwright.async_api import async_playwright, FrameLocator
from playwright_stealth import stealth
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.s3_service import S3Service
from src.services.variant_service import VariantSelector
from src.extractors.rye_client import RyeClient

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


class CartExpiredError(Exception):
    pass


class FailureAlreadyHandledError(Exception):
    pass


class CheckoutAgentService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis
        self.self_healing = SelfHealingService()
        self.s3_service = S3Service()
        self.variant_selector = VariantSelector()
        self._page = None

    async def queue_job(
        self,
        *,
        order_id: int,
        vcn_id: int,
        correlation_id: str | None = None,
        force_failure: bool = False,
    ) -> PurchaseExecution:
        existing = await self.db.scalar(
            select(PurchaseExecution)
            .where(
                PurchaseExecution.order_id == order_id,
                PurchaseExecution.vcn_id == vcn_id,
                PurchaseExecution.status.in_(["queued", "running", "pending_verification"]),
            )
            .order_by(PurchaseExecution.created_at.desc())
        )
        if existing is not None:
            return existing

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
                execution.status = "pending_verification"
                execution.step_reached = "pending_verification"
                await self.db.commit()
                await self.redis.set(
                    f"sk:vcn:pending_verification:{vcn.id}",
                    json.dumps({"execution_id": str(execution.uuid), "order_id": execution.order_id}),
                    ttl=1800,
                )
                return
            await self.redis.delete(f"sk:vcn:pending_verification:{vcn.id}")

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

        except FailureAlreadyHandledError:
            return
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

        if product.platform in {"AMAZON", "SHOPIFY"} and settings.FEATURE_RYE_ENABLED and settings.RYE_API_KEY:
            rye = RyeClient(api_key=settings.RYE_API_KEY, base_url=settings.RYE_API_URL)
            intent = await rye.create_checkout_intent(
                product_url=product.canonical_url or product.url,
                buyer={"email": "customer@sahulatkar.com"},
                payment_token=f"vcn:{vcn.id}",
            )
            final = await rye.poll_checkout_intent(intent.checkout_intent_id)
            if final.status != "COMPLETED":
                raise RuntimeError("Rye checkout failed")
            return {
                "merchant_order_id": final.merchant_order_id,
                "merchant_order_url": product.url,
            }

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
            try:
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )

                page = await context.new_page()
                self._page = page
                await stealth(page)

                for reentry in range(2):
                    try:
                        # Step 1: Navigate
                        execution.step_reached = "navigation"
                        await self.db.commit()
                        await page.goto(product.url, wait_until="networkidle", timeout=settings.CHECKOUT_TIMEOUT_SECONDS * 1000)
                        await self._dismiss_blocking_modal(page)

                        # GAP-07: Variant Selection
                        execution.step_reached = "variant_selection"
                        await self.db.commit()
                        variant_data = self._extract_selected_variants(order)
                        await self._select_variant(page, product, variant_data)

                        if await self._detect_captcha(page):
                            solved = False
                            if settings.FEATURE_CAPTCHA_SOLVING:
                                solved = await self._solve_captcha(page)
                            if not solved:
                                raise RuntimeError("CAPTCHA_REQUIRES_HITL")

                        # Step 2: Add to Cart
                        execution.step_reached = "add_to_cart"
                        await self.db.commit()
                        await self._click_with_retry(
                            page,
                            "button:has-text('Add to Cart'), button:has-text('Buy Now')",
                            "Could not find Add to Cart button",
                            execution_uuid=str(execution.uuid),
                        )
                        await self._dismiss_blocking_modal(page)
                        if await self._is_cart_expired(page):
                            raise CartExpiredError("CART_EXPIRED")

                        actual_total = await self._extract_cart_total(page)
                        if actual_total is not None:
                            expected = Decimal(str(product.cost_price or 0))
                            denominator = expected if expected > Decimal("1") else Decimal("1")
                            drift_pct = ((actual_total - expected) / denominator) * Decimal("100")
                            if drift_pct > Decimal(str(settings.PRICE_DRIFT_THRESHOLD_PCT)):
                                await self._mark_failed(
                                    execution,
                                    "price_mismatch",
                                    f"Cart total drift too high. expected={expected} actual={actual_total} drift_pct={drift_pct.quantize(Decimal('0.01'))}",
                                )
                                raise FailureAlreadyHandledError("PRICE_MISMATCH")

                        # Step 3: Guest Checkout
                        execution.step_reached = "guest_checkout"
                        await self.db.commit()
                        await page.wait_for_load_state("networkidle")
                        await self._dismiss_blocking_modal(page)
                        try:
                            await self._click_with_retry(
                                page,
                                "button:has-text('Guest Checkout'), button:has-text('Checkout as Guest')",
                                "Could not find Guest Checkout",
                                retries=3,
                                execution_uuid=str(execution.uuid),
                            )
                        except Exception:
                            await self._register_throwaway_account(page, execution.id)

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

                        if await self.self_healing.handle_out_of_stock_at_checkout(page):
                            await self._mark_failed(execution, "out_of_stock", "Merchant reported out-of-stock at checkout")
                            raise FailureAlreadyHandledError("OUT_OF_STOCK")

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
                        await self._click_with_retry(
                            page,
                            "button:has-text('Place Order'), button:has-text('Complete Purchase')",
                            "Could not find Submit button",
                            execution_uuid=str(execution.uuid),
                        )

                        # Step 7: Confirmation
                        await page.wait_for_load_state("networkidle")
                        if not await self._is_confirmed(page):
                            execution.status = "pending_verification"
                            execution.step_reached = "checkout_uncertain"
                            await self.db.commit()
                            await self.redis.publish("sk:events:checkout.uncertain", json.dumps({"execution_id": str(execution.uuid), "order_id": execution.order_id}))
                            raise RuntimeError("UNCERTAIN_CHECKOUT_OUTCOME")
                        break
                    except CartExpiredError:
                        if reentry == 0:
                            continue
                        raise

                # Heuristic Order ID extraction
                page_text = await page.content()
                order_id_match = re.search(r"(?:Order|Reference|Confirmation).?\s?#?\s?([A-Z0-9-]{5,20})", page_text, re.IGNORECASE)
                merchant_order_id = order_id_match.group(1) if order_id_match else f"SK-{execution.order_id}"

                return {
                    "merchant_order_id": merchant_order_id,
                    "merchant_order_url": page.url
                }
            finally:
                await browser.close()

    async def _click_with_retry(self, page, selector: str, error_msg: str, retries=1, execution_uuid: str | None = None):
        for _ in range(retries + 1):
            try:
                await page.wait_for_selector(selector, timeout=5000)
                await page.click(selector)
                return
            except Exception:
                healed_selector = await self.self_healing.suggest_selector(
                    page=page,
                    error_context=error_msg,
                    execution_id=execution_uuid,
                    redis=self.redis,
                )
                if healed_selector:
                    try:
                        await page.click(healed_selector)
                        return
                    except Exception:
                        continue
        raise RuntimeError(error_msg)

    async def _human_type(self, target, selector: str, text: str):
        # target can be page or frame_locator
        use_selector = selector
        if hasattr(target, "wait_for_selector"):
            try:
                await target.wait_for_selector(selector, timeout=10000)
            except Exception:
                if target is self._page:
                    field_hint = selector.replace("input", "").replace("[", " ").replace("]", " ").strip() or "form field"
                    healed = await self.self_healing.suggest_form_field_selector(target, field_hint)
                    if healed:
                        use_selector = healed
                        await target.wait_for_selector(use_selector, timeout=5000)
                    else:
                        raise
                else:
                    raise
        
        # GAP-10: Gaussian delay — manual sleep per character for human-like pacing.
        for char in text:
            await target.type(use_selector, char)
            await asyncio.sleep(max(0.02, random.gauss(0.1, 0.04)))

    async def _select_variant(self, page, product: Product, variant_data: dict | None = None):
        return await self.variant_selector.select_variant(page, variant_data or {})

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
            try:
                if await page.query_selector(pattern):
                    return page.frame_locator(pattern)
            except Exception:
                continue
        return None

    async def _capture_screenshot(self, execution: PurchaseExecution, step: str):
        if self._page is None:
            return
        try:
            screenshot = await self._page.screenshot(type="jpeg", quality=70, full_page=True)
            key = f"screenshots/{execution.uuid}/{step}.jpg"
            await self.s3_service.upload_bytes(screenshot, key, content_type="image/jpeg")
            if step == "success_receipt":
                execution.receipt_screenshot_s3 = key
            else:
                execution.screenshot_s3 = key
            await self.db.commit()
        except Exception:
            return

    async def _detect_captcha(self, page) -> bool:
        selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='turnstile']",
        ]
        for selector in selectors:
            if await page.query_selector(selector):
                return True
        return False

    async def _solve_captcha(self, page) -> bool:
        provider = settings.CAPTCHA_PROVIDER
        if provider == "none" or not settings.CAPTCHA_API_KEY:
            return False

        sitekey = await self._extract_captcha_sitekey(page)
        if not sitekey:
            return False

        page_url = page.url or ""
        token: str | None = None
        if provider == "two_captcha":
            token = await self._solve_with_two_captcha(sitekey=sitekey, page_url=page_url)
        elif provider == "capsolver":
            token = await self._solve_with_capsolver(sitekey=sitekey, page_url=page_url)

        if not token:
            return False

        try:
            await page.evaluate(
                """
                (captchaToken) => {
                    const ids = ['g-recaptcha-response', 'h-captcha-response'];
                    for (const id of ids) {
                        const el = document.getElementById(id);
                        if (el) {
                            el.value = captchaToken;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                    document.querySelectorAll('textarea[name="g-recaptcha-response"], textarea[name="h-captcha-response"]').forEach((el) => {
                        el.value = captchaToken;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                }
                """,
                token,
            )
            await asyncio.sleep(1)
            return True
        except Exception:
            return False

    async def _extract_cart_total(self, page) -> Decimal | None:
        selectors = [
            "[data-total]",
            "[class*='total']",
            "[id*='total']",
            ".price-final",
        ]
        for selector in selectors:
            try:
                nodes = await page.query_selector_all(selector)
                for node in nodes:
                    value = await node.get_attribute("data-total")
                    if value:
                        parsed = self._parse_price_to_decimal(value)
                        if parsed is not None:
                            return parsed
                    text = await node.inner_text()
                    parsed = self._parse_price_to_decimal(text)
                    if parsed is not None:
                        return parsed
            except Exception:
                continue

        text = await page.content()
        patterns = [
            r"(?:PKR|Rs\.?|Rs)\s*([\d,]+(?:\.\d{1,2})?)",
            r"Total[^\d]*([\d,]+(?:\.\d{1,2})?)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                try:
                    return Decimal(m.group(1).replace(",", ""))
                except Exception:
                    continue
        return None

    async def _register_throwaway_account(self, page, execution_id: int) -> None:
        email = f"order{execution_id}@checkout.sahulatkar.com"
        password = f"Sk!{execution_id}xY7"
        before_url = page.url
        await self._human_type(page, "input[type='email']", email)
        await self._human_type(page, "input[type='password']", password)
        await self._click_with_retry(page, "button:has-text('Create Account'), button:has-text('Sign Up')", "Could not find account creation button", retries=1)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        post_content = (await page.content()).lower()
        if page.url == before_url and not any(sig in post_content for sig in ["account", "welcome", "checkout", "verification"]):
            raise RuntimeError("THROWAWAY_ACCOUNT_CREATION_FAILED")

    async def _is_confirmed(self, page) -> bool:
        await asyncio.sleep(1)
        content = (await page.content()).lower()
        url = (page.url or "").lower()
        signals = ["order confirmed", "thank you", "order #", "/thank-you", "/order-confirmed", "/success"]
        return any(sig in content or sig in url for sig in signals)

    async def _dismiss_blocking_modal(self, page) -> None:
        selector = await self.self_healing.detect_modal_or_popup(page)
        if selector:
            try:
                await page.click(selector, timeout=1500)
            except Exception:
                return

    async def _is_cart_expired(self, page) -> bool:
        content = (await page.content()).lower()
        return "your cart has expired" in content or "cart expired" in content

    async def _verify_vcn_charge(self, vcn_id: int) -> bool:
        """GAP-21: Poll Redis for Stripe charge confirmation."""
        confirmed_key = f"sk:vcn:charge:confirmed:{vcn_id}"
        legacy_key = f"sk:vcn:pending_verification:{vcn_id}"
        # Webhook should set sk:vcn:charge:confirmed:{vcn_id}=1 when charge is observed.
        for _ in range(10):
            if await self.redis.get(confirmed_key):
                await self.redis.delete(confirmed_key)
                return True
            # Backward-compatibility fallback for older webhook integration.
            if await self.redis.get(legacy_key) == "confirmed":
                await self.redis.delete(legacy_key)
                return True
            await asyncio.sleep(2)
        return False

    async def cancel_job(self, job_uuid: UUID):
        """GAP-06: Mark job cancelled and publish void event."""
        execution = await self.db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == job_uuid))
        if execution is None:
            return

        if execution.status in {"succeeded", "failed", "hitl_escalated", "cancelled"}:
            return

        execution.status = "cancelled"
        execution.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        try:
            items = await self.redis.redis.lrange(QueueName.CHECKOUT, 0, -1)
            for item in items:
                payload_raw = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                try:
                    obj = json.loads(payload_raw)
                except Exception:
                    continue
                if str(obj.get("execution_id")) == str(job_uuid):
                    await self.redis.redis.lrem(QueueName.CHECKOUT, 1, item)
        except Exception:
            pass

        envelope = build_event_envelope(
            event="vcn.void",
            source_service="product-service",
            correlation_id=str(job_uuid),
            payload={
                "execution_id": str(execution.uuid),
                "order_id": execution.order_id,
                "vcn_id": execution.vcn_id,
                "reason": "checkout_cancelled",
            },
        )
        await self.redis.publish(event_channel("vcn.void"), envelope.to_json())

    def _extract_selected_variants(self, order: Order) -> dict[str, str]:
        payload = getattr(order, "selected_variants", None)
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items() if v is not None}
        if isinstance(payload, list):
            out: dict[str, str] = {}
            for item in payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("option_name") or item.get("name")
                value = item.get("selected_value") or item.get("value")
                if name and value:
                    out[str(name)] = str(value)
            return out
        return {}

    def _parse_price_to_decimal(self, raw: str | None) -> Decimal | None:
        if not raw:
            return None
        match = re.search(r"([\d,]+(?:\.\d{1,2})?)", raw)
        if not match:
            return None
        try:
            return Decimal(match.group(1).replace(",", ""))
        except Exception:
            return None

    async def _extract_captcha_sitekey(self, page) -> str | None:
        selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='turnstile']",
        ]
        for selector in selectors:
            el = await page.query_selector(selector)
            if not el:
                continue
            src = await el.get_attribute("src") or ""
            match = re.search(r"[?&]k=([^&]+)", src) or re.search(r"[?&]sitekey=([^&]+)", src)
            if match:
                return match.group(1)
        return None

    async def _solve_with_two_captcha(self, sitekey: str, page_url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                submit = await client.post(
                    "https://2captcha.com/in.php",
                    data={
                        "key": settings.CAPTCHA_API_KEY,
                        "method": "userrecaptcha",
                        "googlekey": sitekey,
                        "pageurl": page_url,
                        "json": 1,
                    },
                )
                submit.raise_for_status()
                data = submit.json()
                if data.get("status") != 1:
                    return None
                captcha_id = data.get("request")
                if not captcha_id:
                    return None

                for _ in range(10):
                    await asyncio.sleep(3)
                    poll = await client.get(
                        "https://2captcha.com/res.php",
                        params={
                            "key": settings.CAPTCHA_API_KEY,
                            "action": "get",
                            "id": captcha_id,
                            "json": 1,
                        },
                    )
                    poll.raise_for_status()
                    pdata = poll.json()
                    if pdata.get("status") == 1:
                        return pdata.get("request")
                    if pdata.get("request") != "CAPCHA_NOT_READY":
                        return None
        except Exception:
            return None
        return None

    async def _solve_with_capsolver(self, sitekey: str, page_url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                create = await client.post(
                    "https://api.capsolver.com/createTask",
                    json={
                        "clientKey": settings.CAPTCHA_API_KEY,
                        "task": {
                            "type": "ReCaptchaV2TaskProxyLess",
                            "websiteURL": page_url,
                            "websiteKey": sitekey,
                        },
                    },
                )
                create.raise_for_status()
                cdata = create.json()
                task_id = cdata.get("taskId")
                if not task_id:
                    return None

                for _ in range(10):
                    await asyncio.sleep(3)
                    poll = await client.post(
                        "https://api.capsolver.com/getTaskResult",
                        json={"clientKey": settings.CAPTCHA_API_KEY, "taskId": task_id},
                    )
                    poll.raise_for_status()
                    pdata = poll.json()
                    if pdata.get("status") == "ready":
                        solution = pdata.get("solution") or {}
                        return solution.get("gRecaptchaResponse") or solution.get("token")
                    if pdata.get("status") == "failed" or pdata.get("errorId"):
                        return None
        except Exception:
            return None
        return None

    async def _load_execution(self, execution_uuid: str) -> PurchaseExecution | None:
        try:
            execution_id = UUID(execution_uuid)
        except Exception:
            return None
        statement = select(PurchaseExecution).where(PurchaseExecution.uuid == execution_id)
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
