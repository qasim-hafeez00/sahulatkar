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
        self.api_secret = api_secret
        self.merchant_iban = merchant_iban
        self.base_url = base_url

    # ── Payment Initiation ─────────────────────────────────────────────────

    async def initiate_ibft(
        self,
        *,
        order_id: int,
        amount_pkr: Decimal,
        payer_iban: str,
        callback_url: str,
    ) -> RaastTransferResult:
        """
        Initiates an IBFT transfer request from payer to SahulatKar.
        Uses httpx to make an async HTTP call to the aggregator.
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

        import httpx
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                headers = {
                    "X-API-Key": self.api_key,
                    "X-Raast-Signature": self._sign_payload(json.dumps(payload).encode()),
                    "Content-Type": "application/json",
                }
                resp = await client.post("/ibft/initiate", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("RAAST_IBFT_HTTP_ERROR") from exc
            logger.warning(f"Raast IBFT call failed: {exc}, returning local stub success")
            data = {"status": "initiated"}

        provider_status = str(data.get("status", "initiated")).lower()
        success = provider_status in {"initiated", "pending", "success", "queued"}
        normalized_status = (
            "success" if provider_status == "success" else
            "pending" if provider_status in {"pending", "queued"} else
            "initiated"
        )

        logger.info(
            "Raast IBFT initiated",
            extra={"order_id": order_id, "gateway_txn_id": gateway_txn_id},
        )
        return RaastTransferResult(
            gateway_txn_id=gateway_txn_id,
            success=success,
            status=normalized_status,
            reference_no=reference_no,
            payload=payload,
        )

    def check_status(self, *, gateway_txn_id: str) -> RaastTransferResult:
        """
        Polls the aggregator for the current status of a Raast transaction.
        Used as a safety net if the webhook is delayed.
        """
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                headers = {"X-API-Key": self.api_key}
                resp = client.get(f"/ibft/status/{gateway_txn_id}", headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("RAAST_STATUS_HTTP_ERROR") from exc
            logger.warning(f"Raast status check failed: {exc}, returning local stub")
            data = {"status": "success", "reference_no": f"SBP-REF-{gateway_txn_id[:8].upper()}"}

        status_raw = str(data.get("status", "pending")).lower()
        return RaastTransferResult(
            gateway_txn_id=gateway_txn_id,
            success=status_raw in {"success", "pending", "initiated", "queued"},
            status="success" if status_raw == "success" else "pending",
            reference_no=data.get("reference_no", f"SBP-REF-{gateway_txn_id[:8].upper()}"),
            payload=data,
        )

    def refund(
        self,
        *,
        gateway_txn_id: str,
        amount_pkr: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        """Initiate a refund for a Raast IBFT transaction."""
        payload = {
            "gateway_txn_id": gateway_txn_id,
            "amount_pkr": str(amount_pkr),
            "reason": reason,
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                headers = {
                    "X-API-Key": self.api_key,
                    "X-Raast-Signature": self._sign_payload(json.dumps(payload).encode()),
                    "Content-Type": "application/json",
                }
                resp = client.post("/ibft/refund", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("RAAST_REFUND_HTTP_ERROR") from exc
            logger.warning(f"Raast refund failed: {exc}, returning local stub")
            data = {"refund_id": f"raast_ref_{uuid4().hex}", "status": "success"}

        return {
            "gateway_refund_id": data.get("refund_id", f"raast_ref_{uuid4().hex}"),
            "status": data.get("status", "success"),
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
        payload = {
            "user_id": user_id,
            "payer_iban": payer_iban,
            "max_amount_pkr": str(max_amount),
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                headers = {
                    "X-API-Key": self.api_key,
                    "X-Raast-Signature": self._sign_payload(json.dumps(payload).encode()),
                    "Content-Type": "application/json",
                }
                resp = client.post("/mandates/setup", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("RAAST_MANDATE_SETUP_HTTP_ERROR") from exc
            logger.warning(f"Raast mandate setup failed: {exc}, returning local stub")
            data = {
                "status": "initiated",
                "mandate_reference": f"MND_{uuid4().hex[:12]}",
                "authorization_url": None,
            }

        return {
            "status": data.get("status", "initiated"),
            "mandate_reference": data.get("mandate_reference", f"MND_{uuid4().hex[:12]}"),
            "authorization_url": data.get("authorization_url"),
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
        payload = {
            "mandate_reference": mandate_reference,
            "amount_pkr": str(amount_pkr),
            "reference_no": reference_no,
        }
        try:
            with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
                headers = {
                    "X-API-Key": self.api_key,
                    "X-Raast-Signature": self._sign_payload(json.dumps(payload).encode()),
                    "Content-Type": "application/json",
                }
                resp = client.post("/mandates/charge", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            if not settings.test_payment_fallbacks_enabled:
                raise RuntimeError("RAAST_MANDATE_CHARGE_HTTP_ERROR") from exc
            logger.warning(f"Raast mandate charge failed: {exc}, returning local stub")
            data = {"gateway_txn_id": f"raast_mnd_{uuid4().hex}", "status": "success"}

        gateway_txn_id = data.get("gateway_txn_id", f"raast_mnd_{uuid4().hex}")
        status_raw = str(data.get("status", "success")).lower()
        return RaastTransferResult(
            gateway_txn_id=gateway_txn_id,
            success=status_raw in {"success", "pending", "initiated", "queued"},
            status="success" if status_raw == "success" else "pending",
            reference_no=reference_no,
            payload=data,
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
