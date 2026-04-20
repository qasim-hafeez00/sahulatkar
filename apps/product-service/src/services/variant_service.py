from __future__ import annotations

import base64
from typing import Any

from openai import AsyncOpenAI

from src.config import settings


class VariantSelector:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def select_variant(self, page, variant_data: dict[str, str]) -> bool:
        if not variant_data:
            return True

        for variant_name, variant_value in variant_data.items():
            selected = await self._select_by_button(page, variant_value)
            if not selected:
                selected = await self._select_by_dropdown(page, variant_name, variant_value)
            if not selected:
                selected = await self._select_by_llm(page, variant_name, variant_value)
            if not selected:
                return False
        return True

    async def _select_by_button(self, page, variant_value: str) -> bool:
        value = (variant_value or "").strip().lower()
        nodes = await page.query_selector_all("button, [role='radio'], [role='option']")
        for node in nodes:
            text = ((await node.inner_text()) or "").strip().lower()
            if text == value:
                disabled = await node.get_attribute("disabled")
                if disabled is not None:
                    return False
                await node.click()
                return await self._verify_selected(node)
        return False

    async def _select_by_dropdown(self, page, variant_name: str, variant_value: str) -> bool:
        selects = await page.query_selector_all("select")
        for select_el in selects:
            await select_el.select_option(label=variant_value)
            selected_value = await select_el.input_value()
            if selected_value:
                return True
        return False

    async def _select_by_llm(self, page, variant_name: str, variant_value: str) -> bool:
        if not self._client or not settings.FEATURE_OPENAI_FALLBACK:
            return False
        try:
            screenshot = await page.screenshot(type="jpeg", quality=70)
            b64 = base64.b64encode(screenshot).decode("utf-8")
            prompt = (
                f"Which element should I click to select {variant_name}={variant_value}? "
                "Return only a CSS selector string."
            )
            response = await self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    }
                ],
                max_tokens=60,
            )
            selector = (response.choices[0].message.content or "").strip().strip("`")
            if not selector:
                return False
            await page.click(selector, timeout=3000)
            return True
        except Exception:
            return False

    async def _verify_selected(self, node) -> bool:
        aria_selected = await node.get_attribute("aria-selected")
        class_name = (await node.get_attribute("class") or "").lower()
        if aria_selected == "true":
            return True
        return any(marker in class_name for marker in ["selected", "active", "chosen"])

    def parse_variants_from_upo(self, upo: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for group in upo.get("variants") or []:
            option_name = group.get("option_name")
            selected = group.get("selected_value")
            if option_name and selected:
                out[str(option_name)] = str(selected)
        return out
