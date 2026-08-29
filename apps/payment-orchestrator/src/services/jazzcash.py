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

from src.config import settings

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
        self.password = password
        self.base_url = base_url

    async def charge(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        phone: str | None = None,
    ) -> JazzCashChargeResult:
        """
        Initiate a direct JazzCash MWALLET charge.
        Uses httpx to make a real REST call to JazzCash.
        """
        gateway_txn_id = f"jc_{uuid4().hex}"
        amount_paisas = int(amount_pkr * 100)

        payload = {
            "pp_MerchantID": self.merchant_id,
            "pp_Amount": str(amount_paisas),
            "pp_TxnRefNo": gateway_txn_id,
            "pp_MobileNumber": phone or "03001234567",
        }

        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.post(
                    "/PaymentGateway/api/Transaction/MobileAccountTransactionOtp",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("JAZZCASH_CHARGE_HTTP_ERROR") from exc
            logger.warning(f"JazzCash charge failed: {exc}, returning local stub success")
            data = {
                "pp_ResponseCode": "000",
                "pp_ResponseMessage": "Success",
            }

        success = data.get("pp_ResponseCode") == "000"
        
        # Merge local fields for return
        payload.update({
            "order_id": order_id,
            "amount_pkr": str(amount_pkr),
            "pp_ResponseCode": data.get("pp_ResponseCode", "000"),
            "pp_ResponseMessage": data.get("pp_ResponseMessage", "Success"),
        })

        logger.info(
            "JazzCash charge executed",
            extra={"order_id": order_id, "gateway_txn_id": gateway_txn_id},
        )
        return JazzCashChargeResult(
            gateway_txn_id=gateway_txn_id,
            success=success,
            status="success" if success else "failed",
            payload=payload,
        )

    async def create_checkout_session(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
    ) -> dict[str, Any]:
        """
        Create a JazzCash checkout session for browser-redirect flows.
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

    def refund(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        """Initiate a refund for a JazzCash transaction."""
        import httpx

        payload = {
            "pp_MerchantID": self.merchant_id,
            "pp_OriginalTxnRefNo": gateway_txn_id,
            "pp_Amount": str(int(amount_pkr * 100)),
            "pp_Reason": reason,
        }

        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                response = client.post("/PaymentGateway/api/Transaction/Refund", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("JAZZCASH_REFUND_HTTP_ERROR") from exc
            logger.warning(f"JazzCash refund failed: {exc}, returning local stub")
            data = {"pp_ResponseCode": "000", "pp_RefundTxnRefNo": f"jc_ref_{uuid4().hex}"}

        success = data.get("pp_ResponseCode") == "000"
        return {
            "gateway_refund_id": data.get("pp_RefundTxnRefNo", f"jc_ref_{uuid4().hex}"),
            "status": "success" if success else "failed",
        }

    def sign_payload(self, body: bytes) -> str:
        digest = hmac.HMAC(
            key=self.password.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        )
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