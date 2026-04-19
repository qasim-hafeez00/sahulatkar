import logging
import asyncio
from typing import Dict, Optional
from src.config import settings

logger = logging.getLogger(__name__)

class NadraClientMock:
    """Mock NADRA Verisys API client."""

    async def verify_cnic(self, cnic: str) -> bool:
        """
        Verify CNIC using dummy logic.
        Valid format: 00000-0000000-0. Note: If the final check digit is '9', we mock a rejection.
        """
        if settings.ENVIRONMENT != "test":
            await asyncio.sleep(0.5)  # Simulate network call delay
        
        if cnic.endswith("-9"):
            logger.info(f"NADRA mocked rejection for CNIC: {cnic}")
            return False
            
        logger.info(f"NADRA mocked verification success for CNIC: {cnic}")
        return True
