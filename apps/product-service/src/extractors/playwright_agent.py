from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal

from src.config import settings

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
            
            # Simple stealth implementation
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            page = await context.new_page()
            try:
                # Block ads and images to save resources
                await page.route("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,svg,css}", lambda r: r.abort())
                
                await page.goto(url, wait_until="domcontentloaded", timeout=settings.EXTRACTION_TIMEOUT_SECONDS * 1000)
                await asyncio.sleep(2)  # Wait for JS to settle
                
                # Distill DOM: Remove scripts, styles, nav, footer
                distilled_text = await page.evaluate("""() => {
                    const removeSelectors = ['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript', 'aside'];
                    removeSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    return document.body.innerText.substring(0, 10000); // Max 10k chars
                }""")
                
                return await self._parse_with_llm(distilled_text, url)
                
            except Exception as e:
                logger.error(f"Playwright extraction failed for {url}: {str(e)}")
                raise
            finally:
                await browser.close()

    async def _parse_with_llm(self, text: str, url: str) -> dict:
        """Calls LLM (Groq or OpenAI) to extract JSON from text."""
        prompt = f"""
        Extract product information from the following text extracted from {url}.
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
                        "model": "llama-3-70b-8192",
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
