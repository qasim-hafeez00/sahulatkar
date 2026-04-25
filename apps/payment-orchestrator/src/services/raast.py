"""
Raast IBFT Integration — SBP's Instant Payment System.

Raast is Pakistan's primary instant payment infrastructure, operated by SBP
and accessible via licensed payment aggregators (1LINK, NayaPay, Finja, etc.).

IMPORTANT: The exact REST API shape varies by aggregator. This module is
designed against the 1LINK / generic SBP IBFT pattern. Replace endpoint
paths and field names according to the chosen aggregator's documentation
when API keys are provisioned.

Authentication: HMAC-SHA256 of the canonical request body using the
shared `RAAST_API_SECRET`. Each request carries an `X-Raast-Signature` header.
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

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RaastTransferResult:
    gateway_txn_id: str
    success: bool
    status: str                     # "initiated" | "pending" | "success" | "failed"
    reference_no: str               # SBP reference number
    payload: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class RaastClient:
    """
    Raast IBFT client.

    In the SBP model, a Raast IBFT transfer requires:
    - Payer's IBAN / Raast ID (linked to user's bank account in their profile)
    - Payee IBAN (SahulatKar's merchant IBAN)
    - Amount in PKR (paisas internally, we convert)
    - Transaction reference

    For down payments, the payer IBAN must be fetched from the user's
    saved payment methods. For installments, the Loan record holds the
    payer IBAN captured at origination.

    TODO: Once aggregator credentials are provisioned, configure:
        RAAST_API_KEY, RAAST_API_SECRET, RAAST_BASE_URL, RAAST_MERCHANT_IBAN
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        merchant_iban: str,
        base_url: str = "https://sandbox.raast-gateway.pk/api/v1",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret or "mock-raast-secret"
        self.merchant_iban = merchant_iban
        self.base_url = base_url

    # ── Payment Initiation ─────────────────────────────────────────────────

    def initiate_ibft(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        payer_iban: str,
        callback_url: str,
    ) -> RaastTransferResult:
        """
        Initiates an IBFT transfer request from payer to SahulatKar.

        In live environment, this makes an async HTTP call to the aggregator.
        The aggregator sends an OTP to the payer's registered mobile number.
        The payer confirms → aggregator calls our webhook.

        Returns a RaastTransferResult with status="initiated".
        """
        gateway_txn_id = f"raast_{uuid4().hex}"
        reference_no = f"SK{order_id:012d}"

        payload = {
            "transaction_id": gateway_txn_id,
            "reference_no": reference_no,
            "payer_iban": payer_iban,
            "payee_iban": self.merchant_iban,
            "amount_paisas": int(amount_pkr * 100),       # SBP uses paisas
            "currency": "PKR",
            "purpose_code": "BNPL_DOWN_PAYMENT",
            "narration": f"SahulatKar Order #{order_id}",
            "callback_url": callback_url,
            "order_id": order_id,
        }

        # TODO: Replace mock with real HTTP call when credentials are provisioned:
        #
        # async with httpx.AsyncClient() as client:
        #     headers = {
        #         "X-API-Key": self.api_key,
        #         "X-Raast-Signature": self._sign_payload(json.dumps(payload).encode()),
        #         "Content-Type": "application/json",
        #     }
        #     resp = await client.post(f"{self.base_url}/ibft/initiate", json=payload, headers=headers, timeout=10)
        #     resp.raise_for_status()
        #     return self._parse_initiation_response(resp.json(), gateway_txn_id)

        logger.info(
            "Raast IBFT initiated (mock)",
            extra={"order_id": order_id, "gateway_txn_id": gateway_txn_id},
        )
        return RaastTransferResult(
            gateway_txn_id=gateway_txn_id,
            success=True,
            status="initiated",
            reference_no=reference_no,
            payload=payload,
        )

    def check_status(self, *, gateway_txn_id: str) -> RaastTransferResult:
        """
        Polls the aggregator for the current status of a Raast transaction.
        Used as a safety net if the webhook is delayed.

        TODO: Implement with real HTTP call when credentials are provisioned.
        """
        logger.info("Raast status check (mock)", extra={"gateway_txn_id": gateway_txn_id})
        return RaastTransferResult(
            gateway_txn_id=gateway_txn_id,
            success=True,
            status="success",
            reference_no=f"SBP-REF-{gateway_txn_id[:8].upper()}",
        )

    def refund(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        """
        Initiate a refund for a Raast IBFT transaction.
        TODO: Integrate with Raast IBFT reversal API.
        """
        from uuid import uuid4
        refund_id = f"raast_ref_{uuid4().hex}"
        logger.info(
            "Raast refund initiated (mock)",
            extra={"gateway_txn_id": gateway_txn_id, "amount_pkr": str(amount_pkr)},
        )
        return {
            "gateway_refund_id": refund_id,
            "status": "success",
        }

    # ── Mandate Management ────────────────────────────────────────────────
    
    def setup_mandate(
        self,
        *,
        user_id: int,
        payer_iban: str,
        max_amount: Decimal,
    ) -> dict[str, Any]:
        """
        Request the payer to authorize a recurring debit mandate.
        In the SBP model, this triggers a mandate authorization request
        to the payer's bank app/USSD.
        """
        mandate_ref = f"MND_{uuid4().hex[:12]}"
        logger.info(
            "Raast mandate setup initiated (mock)",
            extra={"user_id": user_id, "mandate_ref": mandate_ref}
        )
        return {
            "status": "initiated",
            "mandate_reference": mandate_ref,
            "payer_iban": payer_iban,
        }

    def charge_mandate(
        self,
        *,
        mandate_reference: str,
        amount_pkr: Decimal,
        reference_no: str,
    ) -> RaastTransferResult:
        """
        Execute an auto-debit against a previously authorized Raast mandate.
        Used for installment auto-collection.
        """
        gateway_txn_id = f"raast_mnd_{uuid4().hex}"
        logger.info(
            "Raast mandate charge executed (mock)",
            extra={"mandate_ref": mandate_reference, "amount_pkr": str(amount_pkr)}
        )
        return RaastTransferResult(
            gateway_txn_id=gateway_txn_id,
            success=True,
            status="success",
            reference_no=reference_no,
        )

    # ── Signature / Webhook Verification ──────────────────────────────────

    def _sign_payload(self, body: bytes) -> str:
        digest = hmac.HMAC(
            key=self.api_secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        )
        return digest.hexdigest()

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not signature or not body:
            return False
        expected = self._sign_payload(body)
        return hmac.compare_digest(expected, signature)

    def parse_webhook(self, body: bytes) -> dict[str, Any]:
        """
        Parse incoming Raast webhook payload.
        The aggregator sends JSON; the shape depends on the provider:
          - pp_ResponseCode / pp_TxnRefNo (1LINK style, mirrors JazzCash)
          - status / transaction_id / reference_no (REST-native style)
        This implementation handles both patterns.
        """
        data = json.loads(body.decode("utf-8"))
        # Normalise to internal format
        return {
            "gateway_txn_id": data.get("transaction_id") or data.get("pp_TxnRefNo", ""),
            "order_id": data.get("order_id"),
            "amount_pkr": Decimal(str(data.get("amount_pkr") or data.get("pp_Amount", "0"))) / 100
            if data.get("pp_Amount")
            else Decimal(str(data.get("amount_pkr", "0"))),
            "status": data.get("status") or (
                "success" if data.get("pp_ResponseCode") == "000" else "failed"
            ),
            "reference_no": data.get("reference_no") or data.get("pp_SBPReference", ""),
        }
