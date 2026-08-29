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
from urllib.parse import urlencode
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
        base_url: str = "https://sandbox.api.getsafepay.com",
        webhook_secret: str = "",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.webhook_secret = webhook_secret

    async def create_checkout(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
    ) -> SafepayCheckoutResult:
        """
        Create a SafePay hosted checkout session.

        Live-verified against the real SafePay sandbox (200, real tracker
        returned) and cross-checked against getsafepay/safepay-php's
        Base/Payments/Checkout classes: the real order-init call is
        POST {base_url}/order/v1/init with the merchant API key sent as the
        "client" field in the JSON body (no Authorization header at all —
        the original "Bearer {api_key}" against a "/checkout-link" path was
        never a real SafePay endpoint). The hosted page the customer is
        redirected to is a *separate* URL built from the returned tracker
        token, at {base_url}/checkout/pay with the token as the "beacon"
        query param.
        """
        environment = "sandbox" if "sandbox" in self.base_url else "production"
        payload = {
            "client": self.api_key,
            "amount": float(amount_pkr),
            "currency": "PKR",
            "environment": environment,
        }

        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.post("/order/v1/init", json=payload)
                response.raise_for_status()
                data = response.json()
                tracker_token = data["data"]["token"]
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("SAFEPAY_CHECKOUT_HTTP_ERROR") from exc
            logger.warning(f"SafePay checkout call failed: {exc}, falling back to local generated URL")
            tracker_token = f"track_local_{uuid4().hex}"

        checkout_query = urlencode({
            "env": environment,
            "beacon": tracker_token,
            "source": "custom",
            "order_id": str(order_id),
            "redirect_url": callback_url,
            "cancel_url": callback_url,
            "webhooks": "false",
        })
        checkout_url = f"{self.base_url}/checkout/pay?{checkout_query}"
        gateway_txn_id = tracker_token

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
            if not settings.test_payment_fallbacks_enabled:
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
            if not settings.test_payment_fallbacks_enabled:
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
            if not settings.test_payment_fallbacks_enabled:
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
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("SAFEPAY_REFUND_HTTP_ERROR") from exc
            logger.warning(f"SafePay refund failed: {exc}, returning local stub")
            data = {"refund_id": f"sp_rfnd_{uuid4().hex}", "status": "success"}

        return {
            "refund_id": data.get("refund_id", f"sp_rfnd_{uuid4().hex}"),
            "status": data.get("status", "success"),
            "amount_pkr": str(amount_pkr),
        }

    def _sign_data_field(self, data_json: bytes) -> str:
        """HMAC-SHA512 over the encoded "data" field, keyed by the webhook
        secret — matches getsafepay/safepay-php's Verify::webhook() exactly:
        hash_hmac('sha512', json_encode(payload['data'], JSON_UNESCAPED_SLASHES),
        webhookSecret). Distinct from request signing (order/v1/init needs
        no signature at all — see create_checkout) and from the old
        SHA-256-over-raw-body/api_secret scheme this replaces, which was
        never a real SafePay algorithm."""
        digest = hmac.new(
            key=self.webhook_secret.encode("utf-8"),
            msg=data_json,
            digestmod=hashlib.sha512,
        )
        return digest.hexdigest()

    def sign_payload(self, body: bytes) -> str:
        """Test helper: builds the same compact-JSON "data" encoding
        verify_signature expects, from a body that's either already a bare
        data payload or a {"data": {...}} envelope, then signs it."""
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._sign_data_field(body)
        data_field = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
        encoded = json.dumps(data_field, separators=(",", ":")).encode("utf-8")
        return self._sign_data_field(encoded)

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        data_field = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
        encoded = json.dumps(data_field, separators=(",", ":")).encode("utf-8")
        expected = self._sign_data_field(encoded)
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        envelope = json.loads(body.decode("utf-8"))
        data = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
        return {
            "gateway_txn_id": data.get("gateway_txn_id", data.get("tracker", "")),
            "order_id": data.get("order_id"),
            "amount_pkr": Decimal(str(data.get("amount_pkr", data.get("amount", "0")))),
            "status": data.get("status", data.get("state", "")),
        }