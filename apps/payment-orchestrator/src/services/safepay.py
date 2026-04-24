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
        self.api_secret = api_secret or "mock-secret"
        self.base_url = base_url

    def create_checkout(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
    ) -> SafepayCheckoutResult:
        """
        Create a SafePay hosted checkout session.
        Returns a redirect URL the user completes to authorise the payment.

        TODO: Replace mock with real SafePay REST call:
            POST https://api.safepay.pk/order/
        """
        gateway_txn_id = f"sp_{uuid4().hex}"
        checkout_url = (
            f"{self.base_url}/checkout-link"
            f"?token={gateway_txn_id}&amount={float(amount_pkr)}&currency=PKR"
        )
        payload = {
            "order_id": order_id,
            "amount_pkr": str(amount_pkr),
            "currency": "PKR",
            "callback_url": callback_url,
            "gateway_txn_id": gateway_txn_id,
            "environment": "sandbox" if "sandbox" in self.base_url else "production",
        }
        logger.info(
            "SafePay checkout created (mock)",
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
        logger.info(
            "SafePay payment authorized (mock)",
            extra={"gateway_txn_id": gateway_txn_id, "amount_pkr": str(amount_pkr)},
        )
        return {"status": "authorized", "gateway_txn_id": gateway_txn_id}

    def capture_payment(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
    ) -> dict[str, Any]:
        """
        Capture a previously authorized payment.
        """
        logger.info(
            "SafePay payment captured (mock)",
            extra={"gateway_txn_id": gateway_txn_id, "amount_pkr": str(amount_pkr)},
        )
        return {"status": "captured", "gateway_txn_id": gateway_txn_id}

    def void_payment(
        self,
        *,
        gateway_txn_id: str,
    ) -> dict[str, Any]:
        """
        Void an authorized but uncaptured payment.
        """
        logger.info(
            "SafePay payment voided (mock)",
            extra={"gateway_txn_id": gateway_txn_id},
        )
        return {"status": "voided", "gateway_txn_id": gateway_txn_id}

    def initiate_refund(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        """
        Initiate a partial or full refund via SafePay.

        TODO: Replace mock with real SafePay refund API call.
        """
        refund_id = f"sp_rfnd_{uuid4().hex}"
        logger.info(
            "SafePay refund initiated (mock)",
            extra={"gateway_txn_id": gateway_txn_id, "refund_id": refund_id},
        )
        return {"refund_id": refund_id, "status": "success", "amount_pkr": str(amount_pkr)}

    def sign_payload(self, body: bytes) -> str:
        digest = hmac.new(self.api_secret.encode("utf-8"), body, hashlib.sha256)
        return digest.hexdigest()

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        expected = self.sign_payload(body)
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        data = json.loads(body.decode("utf-8"))
        return {
            "gateway_txn_id": data.get("gateway_txn_id", ""),
            "order_id": data.get("order_id"),
            "amount_pkr": Decimal(str(data.get("amount_pkr", "0"))),
            "status": data.get("status", ""),
        }