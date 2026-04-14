from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class JazzCashChargeResult:
    gateway_txn_id: str
    success: bool
    payload: dict[str, Any]


class JazzCashClient:
    def __init__(self, merchant_id: str, password: str, base_url: str = "https://sandbox.jazzcash.com.pk") -> None:
        self.merchant_id = merchant_id
        self.password = password or "mock-secret"
        self.base_url = base_url

    def charge(self, *, order_id: int, amount_pkr: float, phone: str | None = None) -> JazzCashChargeResult:
        gateway_txn_id = f"jc_{uuid4().hex}"
        # Realistic JazzCash response payload simulation
        payload = {
            "pp_MerchantID": self.merchant_id,
            "pp_Amount": str(int(float(amount_pkr) * 100)), # JC often uses paisas
            "pp_TxnRefNo": gateway_txn_id,
            "pp_ResponseCode": "000",
            "pp_ResponseMessage": "Success",
            "order_id": order_id,
            "gateway_txn_id": gateway_txn_id,
            "amount_pkr": float(amount_pkr)
        }
        return JazzCashChargeResult(gateway_txn_id=gateway_txn_id, success=True, payload=payload)

    def sign_payload(self, body: bytes) -> str:
        digest = hmac.new(self.password.encode("utf-8"), body, hashlib.sha256)
        return digest.hexdigest()

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        expected = self.sign_payload(body)
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        return json.loads(body.decode("utf-8"))