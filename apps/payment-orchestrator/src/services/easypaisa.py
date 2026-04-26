"""
EasyPaisa payment gateway client.
"""
from __future__ import annotations

import logging
import hashlib
import hmac
from decimal import Decimal
from typing import Any
from uuid import uuid4

from src.config import settings

logger = logging.getLogger(__name__)

class EasypaisaClient:
    def __init__(
        self,
        store_id: str,
        hash_key: str,
        base_url: str = "https://easypaystg.easypaisa.com.pk",
    ) -> None:
        self.store_id = store_id
        self.hash_key = hash_key
        self.base_url = base_url

    async def charge(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """
        Initiate a direct EasyPaisa charge.
        """
        gateway_txn_id = f"ep_{uuid4().hex}"
        amount_float = float(amount_pkr)

        payload = {
            "storeId": self.store_id,
            "orderId": str(order_id),
            "transactionAmount": str(amount_float),
            "mobileAccountNo": phone or "03451234567",
            "transactionType": "MA",
        }

        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.post(
                    "/easypay/Index.jsf",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("EASYPAISA_CHARGE_HTTP_ERROR") from exc
            logger.warning(f"EasyPaisa charge failed: {exc}, returning local stub success")
            data = {
                "responseCode": "0000",
                "responseMessage": "Success",
            }

        success = data.get("responseCode") == "0000"
        
        logger.info(
            "EasyPaisa charge executed",
            extra={"order_id": order_id, "gateway_txn_id": gateway_txn_id},
        )
        return {
            "gateway_txn_id": gateway_txn_id,
            "success": success,
            "status": "success" if success else "failed",
            "payload": payload,
        }

    async def create_checkout_session(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        callback_url: str,
    ) -> dict[str, Any]:
        gateway_txn_id = f"ep_{uuid4().hex}"
        checkout_url = (
            f"{self.base_url}/checkout?txn={gateway_txn_id}"
            f"&amount={float(amount_pkr)}&currency=PKR"
        )
        return {
            "checkout_url": checkout_url,
            "gateway_txn_id": gateway_txn_id,
        }

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body or not self.hash_key:
            return False
        expected = hmac.new(
            self.hash_key.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_event(self, body: bytes) -> dict[str, Any]:
        import json
        data = json.loads(body.decode("utf-8"))
        return {
            "gateway_txn_id": data.get("transactionId", ""),
            "order_id": data.get("orderId"),
            "amount_pkr": Decimal(str(data.get("transactionAmount", "0"))),
            "status": "success" if data.get("responseCode") == "0000" else "failed",
        }
