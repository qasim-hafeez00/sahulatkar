import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseStorage(ABC):
    @abstractmethod
    async def upload(self, file_path: str, data: bytes) -> str:
        """Upload data to storage and return the path/URL."""
        pass

    @abstractmethod
    async def get_download_url(self, file_path: str) -> str:
        """Return a URL for downloading the file."""
        pass


class LocalStorage(BaseStorage):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def upload(self, file_path: str, data: bytes) -> str:
        full_path = self.base_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)
        return str(full_path.absolute())

    async def get_download_url(self, file_path: str) -> str:
        # For local storage, we just return the local file URI or a placeholder
        full_path = self.base_dir / file_path
        return f"file://{full_path.absolute()}"


class S3Storage(BaseStorage):
    def __init__(self, bucket: str, access_key: str, secret_key: str, endpoint_url: Optional[str] = None):
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise ImportError("S3Storage requires 'boto3' to be installed.")

        self.bucket = bucket
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )

    async def upload(self, file_path: str, data: bytes) -> str:
        self.s3.put_object(Bucket=self.bucket, Key=file_path, Body=data)
        return f"s3://{self.bucket}/{file_path}"

    async def get_download_url(self, file_path: str) -> str:
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": file_path},
            ExpiresIn=3600,
        )


def get_storage_client(settings) -> BaseStorage:
    """Factory to return storage client based on settings."""
    if getattr(settings, "S3_BUCKET", None) and getattr(settings, "S3_ACCESS_KEY", None):
        return S3Storage(
            bucket=settings.S3_BUCKET,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
            endpoint_url=getattr(settings, "S3_ENDPOINT_URL", None),
        )
    return LocalStorage(base_dir=getattr(settings, "CONTRACT_STORAGE_DIR", "./tmp/contracts"))
