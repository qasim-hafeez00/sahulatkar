from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, List, Optional

from playwright.async_api import async_playwright, Page, FrameLocator
from playwright_stealth import stealth

from src.config import settings
from src.services.self_healing import SelfHealingService
from src.services.variant_service import VariantSelector
from sk_shared.models.order import Order
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient

class CheckoutFormFiller:
    def __init__(self, redis: RedisClient) -> None:
        self.redis = redis
        self.self_healing = SelfHealingService()
        self.variant_selector = VariantSelector()
        self._page: Optional[Page] = None
        self._step_callback: Callable[[str], Awaitable[None]] | None = None

    def set_step_callback(self, callback: Callable[[str], Awaitable[None]] | None) -> None:
        self._step_callback = callback

    async def _emit_step(self, step: str) -> None:
        if self._step_callback is not None:
            await self._step_callback(step)

    async def run_checkout(
        self,
        product: Product,
        order: Order,
        pan: str,
        cvv: str,
        attempt_number: int,
        execution_uuid: str,
    ) -> Dict[str, Any]:
        """Core Playwright automation logic for merchant checkout."""
        
        async with async_playwright() as p:
            # Proxy rotation
            proxy_url = settings.BRIGHTDATA_PROXY_URL
            if proxy_url and attempt_number > 1:
                session_id = f"session_{execution_uuid}_{attempt_number}"
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
                        await self._emit_step("navigating")
                        await page.goto(product.url, wait_until="networkidle", timeout=settings.CHECKOUT_TIMEOUT_SECONDS * 1000)
                        await self._dismiss_blocking_modal(page)

                        # Step 1b: Variant Selection
                        await self._emit_step("variant_selection")
                        variant_data = self._extract_selected_variants(order)
                        await self.variant_selector.select_variant(page, variant_data)

                        if await self._detect_captcha(page):
                            solved = False
                            if settings.FEATURE_CAPTCHA_SOLVING:
                                solved = await self._solve_captcha(page)
                            if not solved:
                                raise RuntimeError("CAPTCHA_REQUIRES_HITL")

                        # Step 2: Add to Cart
                        await self._emit_step("add_to_cart")
                        await self._click_with_retry(
                            page,
                            "button:has-text('Add to Cart'), button:has-text('Buy Now')",
                            "Could not find Add to Cart button",
                            execution_uuid=execution_uuid,
                        )
                        await self._dismiss_blocking_modal(page)
                        if await self._is_cart_expired(page):
                            raise RuntimeError("CART_EXPIRED")

                        # Step 2b: Price Drift Detection
                        await self._emit_step("price_drift_check")
                        actual_total = await self._extract_cart_total(page)
                        if actual_total is not None:
                            expected = Decimal(str(product.cost_price or 0))
                            denominator = expected if expected > Decimal("1") else Decimal("1")
                            drift_pct = ((actual_total - expected) / denominator) * Decimal("100")
                            if drift_pct > Decimal(str(settings.PRICE_DRIFT_THRESHOLD_PCT)):
                                raise RuntimeError(f"PRICE_MISMATCH: expected={expected} actual={actual_total} drift={drift_pct.quantize(Decimal('0.01'))}%")

                        # Step 3: Guest Checkout
                        await self._emit_step("guest_checkout")
                        await page.wait_for_load_state("networkidle")
                        await self._dismiss_blocking_modal(page)
                        try:
                            await self._click_with_retry(
                                page,
                                "button:has-text('Guest Checkout'), button:has-text('Checkout as Guest')",
                                "Could not find Guest Checkout",
                                retries=3,
                                execution_uuid=execution_uuid,
                            )
                        except Exception:
                            # Fallback to registration if guest checkout is missing
                            await self._register_throwaway_account(page, execution_uuid)

                        # Step 4: Form Filling
                        await self._emit_step("form_fill")
                        await self._human_type(page, "input[name*='email'], input[type='email']", "customer@sahulatkar.com")
                        await self._human_type(page, "input[name*='firstname']", "Sahulat")
                        await self._human_type(page, "input[name*='lastname']", "Customer")
                        await self._human_type(page, "input[name*='address1'], input[id*='address']", "123 BNPL Street")
                        await self._human_type(page, "input[name*='city']", "Karachi")
                        await self._human_type(page, "input[name*='phone'], input[type='tel']", "03001234567")

                        # Step 4b: Shipping Selection
                        await self._emit_step("shipping_selection")
                        try:
                            await self._click_with_retry(page, "input[type='radio'][name*='shipping'], .shipping-method", "Shipping selection", retries=0)
                        except Exception:
                            pass # Optional step depending on merchant

                        # Step 5: Payment Injection
                        await self._emit_step("payment_injection")
                        if await self.self_healing.handle_out_of_stock_at_checkout(page):
                            raise RuntimeError("OUT_OF_STOCK")

                        payment_frame = await self._get_payment_frame(page)
                        if payment_frame:
                            await self._human_type(payment_frame, "input[name*='cardnumber'], input[id*='card'], input[placeholder*='Card number']", pan)
                            await self._human_type(payment_frame, "input[name*='cvv'], input[id*='cvv'], input[placeholder*='CVV']", cvv)
                        else:
                            await self._human_type(page, "input[name*='cardnumber'], input[id*='card']", pan)
                            await self._human_type(page, "input[name*='cvv'], input[id*='cvv']", cvv)

                        # Step 5b: Review Order Page
                        await self._emit_step("review_order_page")
                        try:
                            # Many sites have an intermediate "Review" or "Continue" before finally placing order
                            await self._click_with_retry(page, "button:has-text('Review'), button:has-text('Continue')", "Review order", retries=0)
                        except Exception:
                            pass

                        # Step 6: Submit Order
                        await self._emit_step("order_submitted")
                        await self._click_with_retry(
                            page,
                            "button:has-text('Place Order'), button:has-text('Complete Purchase')",
                            "Could not find Submit button",
                            execution_uuid=execution_uuid,
                        )


                        # Step 7: Confirmation
                        await page.wait_for_load_state("networkidle")
                        if not await self._is_confirmed(page):
                            raise RuntimeError("UNCERTAIN_CHECKOUT_OUTCOME")
                        await self._emit_step("order_confirmed")
                        break
                    except Exception as e:
                        if "CART_EXPIRED" in str(e) and reentry == 0:
                            continue
                        raise

                # Success Extraction
                page_text = await page.content()
                order_id_match = re.search(r"(?:Order|Reference|Confirmation).?\s?#?\s?([A-Z0-9-]{5,20})", page_text, re.IGNORECASE)
                merchant_order_id = order_id_match.group(1) if order_id_match else f"SK-EXT-{execution_uuid}"

                receipt_screenshot: Optional[bytes] = None
                try:
                    await asyncio.sleep(1)
                    receipt_screenshot = await page.screenshot(type="jpeg", quality=70, full_page=True)
                    await self._emit_step("receipt_captured")
                except Exception:
                    pass

                return {
                    "merchant_order_id": merchant_order_id,
                    "merchant_order_url": page.url,
                    "receipt_screenshot": receipt_screenshot,
                }
            finally:
                self.set_step_callback(None)
                await browser.close()

    async def _click_with_retry(self, page: Page, selector: str, error_msg: str, retries: int = 1, execution_uuid: str | None = None):
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

    async def _human_type(self, target: Page | FrameLocator, selector: str, text: str) -> None:
        """Type text with human-like delays and self-healing."""
        if isinstance(target, FrameLocator):
            locator = target.locator(selector).first
            try:
                await locator.wait_for(state="visible", timeout=10000)
            except Exception:
                return
            for char in text:
                await locator.type(char)
                await asyncio.sleep(max(0.02, random.gauss(0.1, 0.04)))
            return

        use_selector = selector
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

        for char in text:
            await target.type(use_selector, char)
            await asyncio.sleep(max(0.02, random.gauss(0.1, 0.04)))

    async def _get_payment_frame(self, page: Page) -> Optional[FrameLocator]:
        frame_patterns = ["iframe[name*='card']", "iframe[src*='stripe']", "iframe[src*='pay']", "iframe[id*='card']"]
        for pattern in frame_patterns:
            try:
                if await page.query_selector(pattern):
                    return page.frame_locator(pattern)
            except Exception:
                continue
        return None

    async def _detect_captcha(self, page: Page) -> bool:
        selectors = ["iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", "iframe[src*='turnstile']"]
        for selector in selectors:
            if await page.query_selector(selector):
                return True
        return False

    async def _solve_captcha(self, page: Page) -> bool:
        provider = settings.CAPTCHA_PROVIDER
        if provider == "none" or not settings.CAPTCHA_API_KEY:
            return False

        sitekey = await self._extract_captcha_sitekey(page)
        if not sitekey:
            return False

        page_url = page.url or ""
        token: Optional[str] = None
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

    async def _extract_cart_total(self, page: Page) -> Optional[Decimal]:
        selectors = ["[data-total]", "[class*='total']", "[id*='total']", ".price-final"]
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
        patterns = [r"(?:PKR|Rs\.?|Rs)\s*([\d,]+(?:\.\d{1,2})?)", r"Total[^\d]*([\d,]+(?:\.\d{1,2})?)"]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                try:
                    return Decimal(m.group(1).replace(",", ""))
                except Exception:
                    continue
        return None

    async def _register_throwaway_account(self, page: Page, execution_uuid: str | int) -> None:
        email = f"order{execution_uuid}@checkout.sahulatkar.com"
        password = f"Sk!{execution_uuid}xY7"
        before_url = page.url
        await self._human_type(page, "input[type='email']", email)
        await self._human_type(page, "input[type='password']", password)
        await self._click_with_retry(page, "button:has-text('Create Account'), button:has-text('Sign Up')", "Could not find account creation button")
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        post_content = (await page.content()).lower()
        if page.url == before_url and not any(sig in post_content for sig in ["account", "welcome", "checkout", "verification"]):
            raise RuntimeError("THROWAWAY_ACCOUNT_CREATION_FAILED")

    async def _is_confirmed(self, page: Page) -> bool:
        await asyncio.sleep(1)
        content = (await page.content()).lower()
        url = (page.url or "").lower()
        signals = ["order confirmed", "thank you", "order #", "/thank-you", "/order-confirmed", "/success"]
        return any(sig in content or sig in url for sig in signals)

    async def _dismiss_blocking_modal(self, page: Page) -> None:
        selector = await self.self_healing.detect_modal_or_popup(page)
        if selector:
            try:
                await page.click(selector, timeout=1500)
            except Exception:
                return

    async def _is_cart_expired(self, page: Page) -> bool:
        content = (await page.content()).lower()
        return "your cart has expired" in content or "cart expired" in content

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

    def _parse_price_to_decimal(self, raw: str | None) -> Optional[Decimal]:
        if not raw:
            return None
        match = re.search(r"([\d,]+(?:\.\d{1,2})?)", raw)
        if not match:
            return None
        try:
            return Decimal(match.group(1).replace(",", ""))
        except Exception:
            return None

    async def _extract_captcha_sitekey(self, page: Page) -> Optional[str]:
        selectors = ["iframe[src*='recaptcha']", "iframe[src*='hcaptcha']", "iframe[src*='turnstile']"]
        for selector in selectors:
            el = await page.query_selector(selector)
            if not el:
                continue
            src = await el.get_attribute("src") or ""
            match = re.search(r"[?&]k=([^&]+)", src) or re.search(r"[?&]sitekey=([^&]+)", src)
            if match:
                return match.group(1)
        return None

    async def _solve_with_two_captcha(self, sitekey: str, page_url: str) -> Optional[str]:
        import httpx
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
                        params={"key": settings.CAPTCHA_API_KEY, "action": "get", "id": captcha_id, "json": 1},
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

    async def _solve_with_capsolver(self, sitekey: str, page_url: str) -> Optional[str]:
        import httpx
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
