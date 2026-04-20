"""
S3 operations for product-service:
  - Upload bytes (screenshots)
  - Upload from URL (product image caching)
  - Generate presigned GET URLs
"""
import hashlib
import logging

import aioboto3
import httpx
from botocore.exceptions import ClientError

from src.config import settings

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self) -> None:
        # Region and bucket are pulled from settings
        self._session = aioboto3.Session()
        self.bucket_screenshots = settings.S3_BUCKET_SCREENSHOTS

    async def upload_bytes(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        """Upload raw bytes. Returns S3 key."""
        try:
            kwargs = {
                "Bucket": self.bucket_screenshots,
                "Key": key,
                "Body": data,
                "ContentType": content_type,
                "ServerSideEncryption": "aws:kms",
            }
            if settings.AWS_KMS_KEY_ARN:
                kwargs["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ARN
            async with self._session.client("s3", region_name=settings.AWS_REGION) as client:
                await client.put_object(**kwargs)
            return key
        except Exception as exc:
            logger.error("S3 upload failed for key %s: %s", key, exc)
            raise

    async def cache_product_image(self, image_url: str, product_uuid: str) -> str | None:
        """Download external image, re-upload to S3. Returns S3 key or None on failure."""
        if not image_url or not image_url.startswith("http"):
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(image_url)
                if resp.status_code != 200:
                    return None
                
                content_type = resp.headers.get("content-type", "image/jpeg")
                ext = "jpg"
                if "png" in content_type:
                    ext = "png"
                elif "webp" in content_type:
                    ext = "webp"
                
                url_hash = hashlib.sha256(image_url.encode()).hexdigest()[:12]
                key = f"products/{product_uuid}/{url_hash}.{ext}"
                
                return await self.upload_bytes(resp.content, key, content_type)
        except Exception as exc:
            logger.error("Failed to cache product image from %s: %s", image_url, exc)
            return None

    async def presign_url(self, key: str, bucket: str | None = None, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for an S3 object."""
        try:
            async with self._session.client("s3", region_name=settings.AWS_REGION) as client:
                return await client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket or self.bucket_screenshots, "Key": key},
                    ExpiresIn=expires_in,
                )
        except ClientError as exc:
            logger.error("Presigned URL generation failed: %s", exc)
            return ""

    async def delete_object(self, key: str, bucket: str | None = None) -> None:
        async with self._session.client("s3", region_name=settings.AWS_REGION) as client:
            await client.delete_object(Bucket=bucket or self.bucket_screenshots, Key=key)

    async def list_objects(self, prefix: str, bucket: str | None = None) -> list[str]:
        async with self._session.client("s3", region_name=settings.AWS_REGION) as client:
            response = await client.list_objects_v2(Bucket=bucket or self.bucket_screenshots, Prefix=prefix)
        contents = response.get("Contents") or []
        return [obj.get("Key") for obj in contents if obj.get("Key")]
