import logging
import asyncio
from src.config import settings

logger = logging.getLogger(__name__)

class ShuftiClientMock:
    """Mock Shufti Pro OCR/Liveness API client."""

    async def verify_document(self, front_image_url: str, back_image_url: str) -> dict:
        """
        Mock document OCR extraction.
        """
        if settings.ENVIRONMENT != "test":
            await asyncio.sleep(1.0)  # Simulate network call
        
        if "invalid" in front_image_url.lower():
            return {"success": False, "reason": "Blurry document"}
            
        return {
            "success": True,
            "extracted_data": {
                "first_name": "Test",
                "last_name": "User",
                "cnic": "12345-1234567-1",
            }
        }

    async def verify_liveness(self, video_url: str) -> dict:
        """
        Mock liveness check.
        """
        if settings.ENVIRONMENT != "test":
            await asyncio.sleep(1.5) # Simulate processing
        
        if "spoof" in video_url.lower():
             return {"success": False, "reason": "Face spoofing detected"}
             
        return {"success": True}
