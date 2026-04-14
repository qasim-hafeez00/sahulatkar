from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import httpx


class AfterShipClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "aftership-api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )

    async def create_tracking(self, tracking_number: str, slug: str, order_id: int) -> dict[str, Any]:
        if not self.api_key:
            return {
                "id": f"mock-{slug}-{tracking_number}",
                "tracking_number": tracking_number,
                "slug": slug,
                "order_id": str(order_id),
                "tag": "Pending",
            }

        payload = {
            "tracking": {
                "slug": slug,
                "tracking_number": tracking_number,
                "order_id": str(order_id),
            }
        }
        response = await self._client.post("/trackings", json=payload)
        response.raise_for_status()
        body = response.json()
        return body.get("data", {}).get("tracking", {})

    @staticmethod
    def verify_hmac(payload_bytes: bytes, signature: str, secret: str) -> bool:
        if not secret:
            return False

        expected_hex = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_hex, signature):
            return True

        expected_b64 = base64.b64encode(bytes.fromhex(expected_hex)).decode("utf-8")
        return hmac.compare_digest(expected_b64, signature)

    async def aclose(self):
        await self._client.aclose()
