from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class SafepayCheckoutResult:
    checkout_url: str
    gateway_txn_id: str
    payload: dict[str, Any]


class SafepayClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://sandbox.safepay.pk") -> None:
        self.api_key = api_key
        self.api_secret = api_secret or "mock-secret"
        self.base_url = base_url

    def create_checkout(self, *, order_id: int, amount_pkr: float, callback_url: str) -> SafepayCheckoutResult:
        from decimal import Decimal
        gateway_txn_id = f"sp_{uuid4().hex}"
        checkout_url = f"{self.base_url}/checkout-link?token={gateway_txn_id}&amount={float(amount_pkr)}&currency=PKR"
        
        # Real Safepay payload often includes more metadata
        payload = {
            "order_id": order_id,
            "amount_pkr": float(amount_pkr),
            "currency": "PKR",
            "callback_url": callback_url,
            "gateway_txn_id": gateway_txn_id,
            "environment": "sandbox" if "sandbox" in self.base_url else "production"
        }
        return SafepayCheckoutResult(checkout_url=checkout_url, gateway_txn_id=gateway_txn_id, payload=payload)

    def sign_payload(self, body: bytes) -> str:
        digest = hmac.new(self.api_secret.encode("utf-8"), body, hashlib.sha256)
        return digest.hexdigest()

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        expected = self.sign_payload(body)
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        return json.loads(body.decode("utf-8"))