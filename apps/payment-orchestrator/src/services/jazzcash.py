"""
JazzCash payment gateway client.

Supports:
  - Direct charge (MWALLET / MCASH) for installments via billing sweep
  - Checkout session for user-initiated down payments
  - HMAC-SHA256 signature verification for webhooks
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
class JazzCashChargeResult:
    gateway_txn_id: str
    success: bool
    status: str                             # "success" | "failed" | "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


class JazzCashClient:
    """
    JazzCash client for direct wallet charges and webhook verification.

    Direct charges are used for:
      - Installment auto-collection during billing sweep
      - JazzCash wallet down payments (synchronous response)

    The `password` must be the JazzCash integration password (not merchant password).
    """

    def __init__(
        self,
        merchant_id: str,
        password: str,
        base_url: str = "https://sandbox.jazzcash.com.pk",
    ) -> None:
        self.merchant_id = merchant_id
        self.password = password or "mock-secret"
        self.base_url = base_url

    def charge(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        phone: str | None = None,
    ) -> JazzCashChargeResult:
        """
        Initiate a direct JazzCash MWALLET charge.

        JazzCash uses paisas (1/100 PKR) internally, but we accept and
        convert Decimal PKR amounts for consistency.

        TODO: Replace mock with httpx call to JazzCash MobileAccount API:
            POST {base_url}/PaymentGateway/api/Transaction/MobileAccountTransactionOtp
        """
        gateway_txn_id = f"jc_{uuid4().hex}"
        amount_paisas = int(amount_pkr * 100)

        payload = {
            "pp_MerchantID": self.merchant_id,
            "pp_Amount": str(amount_paisas),
            "pp_TxnRefNo": gateway_txn_id,
            "pp_ResponseCode": "000",
            "pp_ResponseMessage": "Success",
            "order_id": order_id,
            "amount_pkr": str(amount_pkr),
        }

        logger.info(
            "JazzCash charge initiated (mock)",
            extra={"order_id": order_id, "gateway_txn_id": gateway_txn_id},
        )
        return JazzCashChargeResult(
            gateway_txn_id=gateway_txn_id,
            success=True,
            status="success",
            payload=payload,
        )

    def create_checkout_session(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
    ) -> dict[str, Any]:
        """
        Create a JazzCash checkout session for browser-redirect flows.
        Returns a dict with checkout_url and gateway_txn_id.

        TODO: Integrate with JazzCash checkout redirect API.
        """
        gateway_txn_id = f"jc_{uuid4().hex}"
        checkout_url = (
            f"{self.base_url}/checkout?txn={gateway_txn_id}"
            f"&amount={int(amount_pkr * 100)}&currency=PKR"
        )
        return {
            "checkout_url": checkout_url,
            "gateway_txn_id": gateway_txn_id,
        }

    def sign_payload(self, body: bytes) -> str:
        digest = hmac.new(self.password.encode("utf-8"), body, hashlib.sha256)
        return digest.hexdigest()

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        expected = self.sign_payload(body)
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        data = json.loads(body.decode("utf-8"))
        return {
            "gateway_txn_id": data.get("pp_TxnRefNo", data.get("gateway_txn_id", "")),
            "order_id": data.get("order_id"),
            "amount_pkr": Decimal(str(data.get("pp_Amount", "0"))) / 100,
            "status": "success" if data.get("pp_ResponseCode") == "000" else "failed",
        }