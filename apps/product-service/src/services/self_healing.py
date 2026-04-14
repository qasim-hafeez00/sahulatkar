from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING, List, Optional

from openai import AsyncOpenAI
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