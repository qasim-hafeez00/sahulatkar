from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import logging

import httpx


@dataclass(slots=True)
class VioletProductResult:
    title: str
    price: Decimal
    currency: str
    availability: str
    images: list[str]
    variants: list[dict]
    merchant: dict


@dataclass(slots=True)
class VioletOrderResult:
    order_id: str
    status: str
    total: Decimal | None


logger = logging.getLogger(__name__)


class VioletClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _should_retry(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    async def _request_with_retry(self, client: httpx.AsyncClient, method: str, endpoint: str, **kwargs) -> httpx.Response:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.request(method, endpoint, **kwargs)
                if not self._should_retry(response.status_code):
                    return response
                if attempt == max_attempts:
                    return response
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2 ** (attempt - 1), 4)
                await asyncio.sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == max_attempts:
                    raise
                await asyncio.sleep(min(2 ** (attempt - 1), 4))

        raise RuntimeError("Unexpected retry loop termination")

    @staticmethod
    def _map_availability(value: str | None) -> str:
        mapping = {
            "IN_STOCK": "in_stock",
            "OUT_OF_STOCK": "out_of_stock",
            "LOW_STOCK": "limited",
            "PREORDER": "limited",
        }
        return mapping.get((value or "").upper(), "unknown")

    async def fetch_product(self, url: str) -> VioletProductResult | None:
        endpoint = f"{self.base_url}/v1/catalog/products"
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                resp = await self._request_with_retry(client, "GET", endpoint, headers=self._headers(), params={"url": url})
            if resp.status_code != 200:
                return None
            data = resp.json() or {}
            return VioletProductResult(
                title=data.get("title") or data.get("name") or "",
                price=Decimal(str(data.get("price") or 0)),
                currency=(data.get("currency") or "PKR").upper(),
                availability=self._map_availability(data.get("inventory_status")),
                images=[img for img in (data.get("images") or []) if isinstance(img, str)],
                variants=data.get("variants") or [],
                merchant=data.get("merchant") or {},
            )
        except Exception as exc:
            logger.warning("Violet fetch_product failed: %s", exc)
            return None

    async def create_channel_order(self, cart_id: str, payment: dict) -> VioletOrderResult | None:
        endpoint = f"{self.base_url}/v1/orders"
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                resp = await self._request_with_retry(client, "POST", endpoint, headers=self._headers(), json={"cart_id": cart_id, "payment": payment})
            if resp.status_code != 200:
                return None
            data = resp.json() or {}
            return VioletOrderResult(
                order_id=data.get("order_id") or data.get("id") or "",
                status=data.get("status") or "unknown",
                total=Decimal(str(data.get("total"))) if data.get("total") is not None else None,
            )
        except Exception as exc:
            logger.warning("Violet create_channel_order failed: %s", exc)
            return None
