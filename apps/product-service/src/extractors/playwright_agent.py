from __future__ import annotations

import asyncio
import base64
import json
import logging
from decimal import Decimal
import re

from src.config import settings
from playwright_stealth import stealth

logger = logging.getLogger(__name__)

class PlaywrightExtractionAgent:
    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.openai_api_key = settings.OPENAI_API_KEY

    async def extract(self, url: str) -> dict:
        """
        Main entry point for Playwright-based extraction.
        1. Launches Playwright
        2. Navigates to URL with stealth
        3. Extracts distilled DOM
        4. Calls LLM to parse into JSON
        """
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1366, "height": 768}
            )
            
            page = await context.new_page()
            await stealth(page)
            try:
                async def _route(route):
                    req = route.request
                    if req.resource_type in {"image", "font", "media", "stylesheet"}:
                        await route.abort()
                        return
                    target = req.url.lower()
                    if any(tracker in target for tracker in ["google-analytics.com", "doubleclick.net", "facebook.net"]):
                        await route.abort()
                        return
                    await route.continue_()

                await page.route("**/*", _route)
                
                await page.goto(url, wait_until="domcontentloaded", timeout=settings.EXTRACTION_TIMEOUT_SECONDS * 1000)
                platform = self._detect_platform(url)
                await self._platform_wait(page, platform)

                distilled_text = await self._distill_product_text(page)
                parsed = await self._parse_with_llm(distilled_text, url, platform)
                if not self._is_valid(parsed):
                    await self._retry_with_scroll(page)
                    distilled_text = await self._distill_product_text(page)
                    parsed = await self._parse_with_llm(distilled_text, url, platform)
                    if not self._is_valid(parsed):
                        raise ValueError("EXTRACTION_VALIDATION_FAILED")

                screenshot = await page.screenshot(type="jpeg", quality=50, full_page=True)
                parsed["debug_screenshot_b64"] = base64.b64encode(screenshot).decode("utf-8")
                parsed.setdefault("confidence", 0.85)
                return parsed
                
            except Exception as e:
                logger.error(f"Playwright extraction failed for {url}: {str(e)}")
                raise
            finally:
                await browser.close()

    async def _parse_with_llm(self, text: str, url: str, platform: str) -> dict:
        """Calls LLM (Groq or OpenAI) to extract JSON from text."""
        platform_hint = "This is a Daraz product page - prices are usually in PKR." if platform == "DARAZ" else ""
        prompt = f"""
        Extract product information from the following product-page text extracted from {url}.
        Platform: {platform}. {platform_hint}
        Return ONLY a JSON object with the following keys:
        - title (string)
        - price (number, current sale price)
        - currency (string, default "PKR")
        - availability (string: "in_stock", "out_of_stock", "preorder", or "unknown")
        - image_url (string, main product image)
        - description (string, max 200 chars)

        Text:
        {text}
        """

        if settings.FEATURE_GROQ_ENABLED and self.groq_api_key:
            return await self._call_groq(prompt)
        elif settings.FEATURE_OPENAI_FALLBACK and self.openai_api_key:
            return await self._call_openai(prompt)
        else:
            raise ValueError("No LLM provider available for Tier 3 extraction")

    async def _call_groq(self, prompt: str) -> dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.1-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "response_format": {"type": "json_object"}
                    }
                )
                resp.raise_for_status()
                return json.loads(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            logger.error(f"Groq call failed: {str(e)}")
            raise

    async def _call_openai(self, prompt: str) -> dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "response_format": {"type": "json_object"}
                    }
                )
                resp.raise_for_status()
                return json.loads(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            logger.error(f"OpenAI call failed: {str(e)}")
            raise

    async def _platform_wait(self, page, platform: str) -> None:
        if platform == "DARAZ":
            try:
                await page.wait_for_selector(".pdp-product-title", timeout=4000)
                return
            except Exception:
                pass
        elif platform == "AMAZON":
            try:
                await page.wait_for_selector("#productTitle", timeout=4000)
                return
            except Exception:
                pass
        await asyncio.sleep(2)

    async def _distill_product_text(self, page) -> str:
        selectors = ["main", "article", "[class*='product']", "[class*='item']", "[class*='pdp']", "[class*='detail']"]
        for selector in selectors:
            node = await page.query_selector(selector)
            if node is not None:
                text = (await node.inner_text() or "").strip()
                if len(text) > 200:
                    return text[:10000]
        body = await page.inner_text("body")
        return (body or "")[:10000]

    async def _retry_with_scroll(self, page) -> None:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.5)")
        await asyncio.sleep(0.7)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.7)

    def _detect_platform(self, url: str) -> str:
        target = url.lower()
        if "daraz" in target:
            return "DARAZ"
        if "amazon" in target:
            return "AMAZON"
        if "/products/" in target:
            return "SHOPIFY"
        return "CUSTOM"

    def _is_valid(self, data: dict) -> bool:
        title = str(data.get("title") or "").strip()
        availability = str(data.get("availability") or "").strip().lower()
        if len(title) < 3:
            return False
        try:
            price = Decimal(str(data.get("price") or 0))
        except Exception:
            return False
        if price <= 0:
            return False
        return availability in {"in_stock", "out_of_stock", "preorder", "limited", "unknown"}
