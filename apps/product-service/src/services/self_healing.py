from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING, List, Optional

from openai import AsyncOpenAI
from sk_shared.redis_client import RedisClient
from src.config import settings

if TYPE_CHECKING:
    from playwright.async_api import Page


class SelfHealingService:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # PCI/security fix: once live cardholder data (PAN/CVV) may have been
        # typed into the checkout page, self-healing must never take or send
        # another screenshot of it to OpenAI — a screenshot taken any time
        # from the "Payment Injection" checkout step onward (including of an
        # iframe-hosted payment form) can capture live, unmasked card data.
        # `mark_payment_data_injected()` is called by `CheckoutFormFiller`
        # right as that step begins (before any card field is typed, since a
        # selector-not-found on a *later* field, e.g. CVV, could otherwise
        # trigger self-healing after an *earlier* field, e.g. PAN, is already
        # visible on the page). This flag is checked at the very top of every
        # self-healing entry point below — not by the caller — so a future
        # call site can't accidentally bypass the guard by forgetting to
        # check it first.
        self.payment_data_injected: bool = False

    def mark_payment_data_injected(self) -> None:
        """Call once the checkout session has reached (or is about to reach)
        the point where live PAN/CVV may be typed into the page. Irreversible
        for the lifetime of this service instance — there is no matching
        "unmark", since a single `SelfHealingService` is scoped to a single
        checkout job (see `CheckoutFormFiller.__init__`) and card data, once
        it may be on screen, must stay off-limits to self-healing for the
        rest of that job."""
        self.payment_data_injected = True

    async def suggest_selector(
        self,
        *,
        page: Optional[Page] = None,
        error_context: str,
        execution_id: str | None = None,
        redis: RedisClient | None = None,
        fallback_selectors: List[str] | None = None,
    ) -> str | None:
        """
        Attempts to find a CSS selector to proceed by using GPT-4o Vision to analyze
        a screenshot of the current page state.
        """
        if self.payment_data_injected:
            # Fail closed: never screenshot the page once cardholder data may
            # be visible on it. Returning None (instead of even a heuristic
            # match) makes the caller (`_click_with_retry`) exhaust its
            # retries and raise, which routes the job to HITL manual review
            # via CheckoutAgentService.process_job's existing failure/HITL
            # escalation path — no new escalation mechanism needed.
            return None

        # 1. Heuristic fallbacks first (fast)
        lowered = error_context.lower()
        if "guest" in lowered and "checkout" in lowered:
            return "button:has-text('Guest Checkout')"
        if "place order" in lowered:
            return "button:has-text('Place Order')"

        # 2. If no heuristic, use VLM if enabled
        if not settings.FEATURE_OPENAI_FALLBACK or not settings.OPENAI_API_KEY or not page:
            return fallback_selectors[0] if fallback_selectors else None

        if execution_id and redis:
            calls = await redis.incr(f"sk:vlm:calls:{execution_id}")
            if calls == 1:
                await redis.expire(f"sk:vlm:calls:{execution_id}", 3600)
            if calls > 5:
                return fallback_selectors[0] if fallback_selectors else None

        try:
            screenshot = await page.screenshot(type="jpeg", quality=70)
            base64_image = base64.b64encode(screenshot).decode("utf-8")

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"The autonomous checkout agent is stuck. Error: {error_context}. "
                                    "Analyze the screenshot and return the CSS selector for the next button "
                                    "to click to proceed with the checkout. Return ONLY the selector."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
                max_tokens=50,
            )
            selector = response.choices[0].message.content.strip()
            # Basic sanitization
            if selector.startswith("`") and selector.endswith("`"):
                selector = selector[1:-1]
            return selector
        except Exception:
            # Final fallback to regex/provided selectors
            if fallback_selectors:
                return fallback_selectors[0]
            match = re.search(r"#[a-zA-Z0-9_-]+", error_context)
            return match.group(0) if match else None

    async def detect_modal_or_popup(self, page: Page) -> str | None:
        candidates = [
            "button:has-text('Accept')",
            "button:has-text('I Agree')",
            "button:has-text('Close')",
            "button[aria-label='Close']",
            "[id*='cookie'] button",
            "[class*='modal'] button[aria-label='Close']",
        ]
        for selector in candidates:
            if await page.query_selector(selector):
                return selector
        return None

    async def handle_out_of_stock_at_checkout(self, page: Page) -> bool:
        text = (await page.content()).lower()
        signals = ["out of stock", "sold out", "unavailable", "no longer available"]
        return any(signal in text for signal in signals)

    async def suggest_form_field_selector(self, page: Page, field_purpose: str) -> str | None:
        if self.payment_data_injected:
            # Same fail-closed guard as `suggest_selector` above: never
            # screenshot the page once cardholder data may be on it.
            return None
        if not settings.FEATURE_OPENAI_FALLBACK or not settings.OPENAI_API_KEY:
            return None
        try:
            screenshot = await page.screenshot(type="jpeg", quality=70)
            base64_image = base64.b64encode(screenshot).decode("utf-8")
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Identify the CSS selector for the {field_purpose}. Return only the selector.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                            },
                        ],
                    }
                ],
                max_tokens=60,
            )
            return (response.choices[0].message.content or "").strip().strip("`")
        except Exception:
            return None