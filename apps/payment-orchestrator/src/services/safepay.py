"""
SafePay payment gateway client.

Supports:
  - Checkout session creation (browser redirect)
  - Webhook event parsing and HMAC signature verification
  - Refund initiation (when credentials are provisioned)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SafepayCheckoutResult:
    checkout_url: str
    gateway_txn_id: str
    payload: dict[str, Any] = field(default_factory=dict)


class SafepayClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://sandbox.safepay.pk",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url

    async def create_checkout(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
    ) -> SafepayCheckoutResult:
        """
        Create a SafePay hosted checkout session.
        Uses httpx to make a real REST call to the SafePay API.
        """
        gateway_txn_id = f"sp_{uuid4().hex}"
        payload = {
            "order_id": order_id,
            "amount_pkr": str(amount_pkr),
            "currency": "PKR",
            "callback_url": callback_url,
            "gateway_txn_id": gateway_txn_id,
            "environment": "sandbox" if "sandbox" in self.base_url else "production",
        }

        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.post(
                    "/checkout-link",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                response.raise_for_status()
                # Assuming the real API returns something like this
                data = response.json()
                checkout_url = data.get("checkout_url", f"{self.base_url}/checkout-link?token={gateway_txn_id}")
        except httpx.HTTPError as exc:
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("SAFEPAY_CHECKOUT_HTTP_ERROR") from exc
            logger.warning(f"SafePay checkout call failed: {exc}, falling back to local generated URL")
            checkout_url = f"{self.base_url}/checkout-link?token={gateway_txn_id}&amount={float(amount_pkr)}&currency=PKR"

        logger.info(
            "SafePay checkout created",
            extra={"order_id": order_id, "gateway_txn_id": gateway_txn_id},
        )
        return SafepayCheckoutResult(
            checkout_url=checkout_url,
            gateway_txn_id=gateway_txn_id,
            payload=payload,
        )

    def authorize_payment(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
    ) -> dict[str, Any]:
        """
        Explicitly authorize a payment (reserve funds).
        In SafePay, this is usually part of the checkout flow, but we can verify it here.
        """
        import httpx
        payload = {"gateway_txn_id": gateway_txn_id, "amount_pkr": str(amount_pkr)}
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                response = client.post(
                    "/payments/authorize",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("SAFEPAY_AUTHORIZE_HTTP_ERROR") from exc
            logger.warning(f"SafePay authorize failed: {exc}, returning local stub")
            data = {"status": "authorized"}

        return {"status": data.get("status", "authorized"), "gateway_txn_id": gateway_txn_id}

    def capture_payment(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
    ) -> dict[str, Any]:
        """
        Capture a previously authorized payment.
        """
        import httpx
        payload = {"gateway_txn_id": gateway_txn_id, "amount_pkr": str(amount_pkr)}
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                response = client.post(
                    "/payments/capture",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("SAFEPAY_CAPTURE_HTTP_ERROR") from exc
            logger.warning(f"SafePay capture failed: {exc}, returning local stub")
            data = {"status": "captured"}

        return {"status": data.get("status", "captured"), "gateway_txn_id": gateway_txn_id}

    def void_payment(
        self,
        *,
        gateway_txn_id: str,
    ) -> dict[str, Any]:
        """
        Void an authorized but uncaptured payment.
        """
        import httpx
        payload = {"gateway_txn_id": gateway_txn_id}
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                response = client.post(
                    "/payments/void",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("SAFEPAY_VOID_HTTP_ERROR") from exc
            logger.warning(f"SafePay void failed: {exc}, returning local stub")
            data = {"status": "voided"}

        return {"status": data.get("status", "voided"), "gateway_txn_id": gateway_txn_id}

    def initiate_refund(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        """Initiate a partial or full refund via SafePay."""
        import httpx
        payload = {
            "gateway_txn_id": gateway_txn_id,
            "amount_pkr": str(amount_pkr),
            "reason": reason,
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                response = client.post(
                    "/payments/refund",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("SAFEPAY_REFUND_HTTP_ERROR") from exc
            logger.warning(f"SafePay refund failed: {exc}, returning local stub")
            data = {"refund_id": f"sp_rfnd_{uuid4().hex}", "status": "success"}

        return {
            "refund_id": data.get("refund_id", f"sp_rfnd_{uuid4().hex}"),
            "status": data.get("status", "success"),
            "amount_pkr": str(amount_pkr),
        }

    def _sign_payload(self, body: bytes) -> str:
        digest = hmac.new(
            key=self.api_secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        )
        return digest.hexdigest()

    def sign_payload(self, body: bytes) -> str:
        """Backward-compatible alias used by tests; prefer _sign_payload."""
        return self._sign_payload(body)

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        expected = self._sign_payload(body)
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        data = json.loads(body.decode("utf-8"))
        return {
            "gateway_txn_id": data.get("gateway_txn_id", ""),
            "order_id": data.get("order_id"),
            "amount_pkr": Decimal(str(data.get("amount_pkr", "0"))),
            "status": data.get("status", ""),
        }