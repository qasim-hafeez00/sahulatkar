import asyncio
import logging
import re
import secrets
from datetime import datetime, timezone

from src.config import settings

from .base import NadraProvider

logger = logging.getLogger(__name__)

_CNIC_PATTERN = re.compile(r"^\d{5}-\d{7}-\d$")


class MockNadraProvider(NadraProvider):
    """Deterministic CNIC verification simulator — no network call.

    Mirrors the shape of a real NADRA Verisys response (malformed input,
    registry miss, verified — each logged with its own reference id) closely
    enough that switching NADRA_PROVIDER to "verisys" later changes only
    which class kyc.py talks to, never how the KYC flow behaves. Convention
    for exercising each outcome in dev/test: a CNIC ending in "-9" simulates
    a registry mismatch/rejection, matching the original NadraClientMock.
    """

    async def verify_cnic(self, cnic: str) -> bool:
        reference_id = f"MOCK-{secrets.token_hex(4).upper()}"

        if settings.ENVIRONMENT != "test":
            await asyncio.sleep(0.5)  # Simulate a NADRA Verisys network round-trip

        if not _CNIC_PATTERN.match(cnic or ""):
            logger.info(
                "NADRA mock: malformed CNIC rejected",
                extra={"reference_id": reference_id, "cnic": cnic},
            )
            return False

        if cnic.endswith("-9"):
            logger.info(
                "NADRA mock: simulated registry mismatch",
                extra={"reference_id": reference_id, "cnic": cnic},
            )
            return False

        logger.info(
            "NADRA mock: verification succeeded",
            extra={
                "reference_id": reference_id,
                "cnic": cnic,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True
