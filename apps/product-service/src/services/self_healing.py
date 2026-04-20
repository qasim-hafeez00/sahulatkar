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