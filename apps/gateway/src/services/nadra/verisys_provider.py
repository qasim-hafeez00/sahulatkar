import logging

import httpx

from src.config import settings

from .base import NadraProvider

logger = logging.getLogger(__name__)


class NadraVerisysProvider(NadraProvider):
    """Real NADRA Verisys client.

    NADRA does not publish a self-serve API spec — the request/response
    field names below are placeholders. Once enterprise onboarding is
    approved, confirm the real contract against NADRA's integration
    documentation and adjust _build_request_body()/_parse_response() —
    auth, timeout, retries, and error handling are already wired and
    shouldn't need to change.
    """

    def __init__(self) -> None:
        if not settings.NADRA_API_URL or not settings.NADRA_API_KEY:
            raise RuntimeError(
                "NADRA_PROVIDER=verisys requires NADRA_API_URL and NADRA_API_KEY to be set."
            )
        self._base_url = settings.NADRA_API_URL.rstrip("/")
        self._api_key = settings.NADRA_API_KEY
        self._channel_id = settings.NADRA_CHANNEL_ID
        self._timeout = settings.NADRA_TIMEOUT_SECONDS

    def _build_request_body(self, cnic: str) -> dict:
        # TODO(nadra-integration): confirm exact field names against NADRA's
        # Verisys integration spec once onboarding is complete.
        body = {"cnic": cnic}
        if self._channel_id:
            body["channel_id"] = self._channel_id
        return body

    def _parse_response(self, payload: dict) -> bool:
        # TODO(nadra-integration): confirm the real success field name/shape.
        return bool(payload.get("verified") or payload.get("status") == "VERIFIED")

    async def verify_cnic(self, cnic: str) -> bool:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/verify",
                    json=self._build_request_body(cnic),
                    headers=headers,
                )
                response.raise_for_status()
                return self._parse_response(response.json())
        except httpx.HTTPError as exc:
            logger.error("NADRA Verisys API error: %s", exc)
            raise
