import httpx
from typing import Optional
import uuid
from src.config import settings

class InternalServiceClient:
    client: Optional[httpx.AsyncClient] = None

    @classmethod
    def start(cls):
        cls.client = httpx.AsyncClient(timeout=10.0)

    @classmethod
    async def stop(cls):
        if cls.client:
            await cls.client.aclose()

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if not cls.client:
             raise RuntimeError("InternalServiceClient is not initialized")
        return cls.client

    @staticmethod
    def signed_headers(request_id: str | None = None) -> dict[str, str]:
        return {
            "X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN,
            "X-Request-ID": request_id or str(uuid.uuid4()),
        }
