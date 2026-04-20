from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
import logging

import httpx


class RyeCheckoutError(Exception):
    pass


class RyeCheckoutTimeout(Exception):
    pass


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RyeProductResult:
    title: str
    price: Decimal
    currency: str
    availability: str
    images: list[str]
    description: str | None = None
    variants: list[dict] | None = None
    sku: str | None = None


@dataclass(slots=True)
class RyeCheckoutResult:
    checkout_intent_id: str
    status: str
    merchant_order_id: str | None = None
    total_charged: Decimal | None = None


class RyeClient:
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
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.request(method, endpoint, **kwargs)
                if not self._should_retry(response.status_code):
                    return response

                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2 ** (attempt - 1), 4)
                if attempt == max_attempts:
                    return response
                await asyncio.sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt == max_attempts:
                    raise
                await asyncio.sleep(min(2 ** (attempt - 1), 4))

        if last_exc is not None:
            raise last_exc
        raise RyeCheckoutError("Rye request failed without response")

    @staticmethod
    def _map_availability(value: str | None) -> str:
        mapping = {
            "IN_STOCK": "in_stock",
            "OUT_OF_STOCK": "out_of_stock",
            "PREORDER": "limited",
            "BACKORDER": "limited",
            "UNKNOWN": "unknown",
        }
        return mapping.get((value or "").upper(), "unknown")

    @staticmethod
    def _decimal_from_subunits(subunits: int | str | None) -> Decimal:
        amount_subunits = int(subunits or 0)
        return (Decimal(amount_subunits) / Decimal("100")).quantize(Decimal("0.01"))

    async def fetch_product(self, url: str) -> RyeProductResult | None:
        timeout = httpx.Timeout(40.0)
        endpoint = f"{self.base_url}/v1/products"
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await self._request_with_retry(client, "GET", endpoint, params={"url": url}, headers=self._headers())
            except Exception as exc:
                logger.warning("Rye fetch_product request failed: %s", exc)
                return None

            if resp.status_code != 200:
                return None

            try:
                data = resp.json()
            except Exception:
                return None

            price = self._decimal_from_subunits((data.get("price") or {}).get("amountSubunits"))
            return RyeProductResult(
                title=data.get("title") or data.get("name") or "",
                price=price,
                currency=((data.get("price") or {}).get("currency") or "PKR").upper(),
                availability=self._map_availability(data.get("availability")),
                images=[img for img in (data.get("images") or []) if isinstance(img, str)],
                description=data.get("description"),
                variants=data.get("variants") or [],
                sku=data.get("sku"),
            )

    async def create_checkout_intent(self, product_url: str, buyer: dict, payment_token: str) -> RyeCheckoutResult:
        timeout = httpx.Timeout(40.0)
        endpoint = f"{self.base_url}/v1/checkout-intents"
        payload = {
            "productUrl": product_url,
            "buyer": buyer,
            "paymentToken": payment_token,
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await self._request_with_retry(client, "POST", endpoint, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                raise RyeCheckoutError(f"Rye checkout intent failed with status={resp.status_code}")
            try:
                data = resp.json()
            except Exception as exc:
                raise RyeCheckoutError("Rye checkout intent returned invalid JSON") from exc
            return RyeCheckoutResult(
                checkout_intent_id=data.get("checkout_intent_id") or data.get("id") or "",
                status=data.get("status") or "unknown",
                merchant_order_id=data.get("merchant_order_id"),
                total_charged=Decimal(str(data.get("total_charged"))) if data.get("total_charged") is not None else None,
            )

    async def poll_checkout_intent(self, intent_id: str, max_polls: int = 12, interval_seconds: float = 5.0) -> RyeCheckoutResult:
        timeout = httpx.Timeout(40.0)
        endpoint = f"{self.base_url}/v1/checkout-intents/{intent_id}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            for _ in range(max_polls):
                try:
                    resp = await self._request_with_retry(client, "GET", endpoint, headers=self._headers())
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    raise RyeCheckoutTimeout(f"Checkout poll transport failed for intent {intent_id}") from exc
                if resp.status_code >= 400:
                    raise RyeCheckoutError(f"Rye checkout poll failed with status={resp.status_code}")
                try:
                    data = resp.json()
                except Exception as exc:
                    raise RyeCheckoutError("Rye checkout poll returned invalid JSON") from exc
                status = (data.get("status") or "").upper()
                result = RyeCheckoutResult(
                    checkout_intent_id=intent_id,
                    status=status,
                    merchant_order_id=data.get("merchant_order_id"),
                    total_charged=Decimal(str(data.get("total_charged"))) if data.get("total_charged") is not None else None,
                )
                if status in {"COMPLETED", "FAILED"}:
                    return result
                await asyncio.sleep(interval_seconds)

        raise RyeCheckoutTimeout(f"Checkout intent {intent_id} was not finalized in time")
