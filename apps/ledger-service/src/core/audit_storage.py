"""
S3 Audit Storage Support

Provides backend-agnostic audit file persistence with support for
both local filesystem and AWS S3 storage. Enables durable audit trails
that survive pod restarts and cluster failures.

Configuration:
- AUDIT_STORAGE_BACKEND: 'filesystem' (default) or 's3'
- AUDIT_S3_BUCKET: S3 bucket name (required if backend='s3')
- AUDIT_S3_PREFIX: Prefix/path in bucket (default: 'ledger-audit/')
- AUDIT_S3_REGION: AWS region (default: 'us-east-1')
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import aiofiles


logger = logging.getLogger(__name__)


class AuditStorageBackend(ABC):
    """Abstract base for audit file storage backends."""

    @abstractmethod
    async def append_line(self, filename: str, data: dict[str, Any]) -> None:
        """Append a JSON line to an audit file."""
        pass

    @abstractmethod
    async def read_lines(self, filename: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Read all JSON lines from an audit file."""
        pass

    @abstractmethod
    async def list_files(self, prefix: str = "") -> list[str]:
        """List audit files matching prefix."""
        pass

    @abstractmethod
    async def get_file_size(self, filename: str) -> int:
        """Get size in bytes of audit file."""
        pass


class FilesystemAuditBackend(AuditStorageBackend):
    """
    Local filesystem storage for audit files.
    
    Simple but not highly available. Requires PersistentVolume in K8s
    or pod affinity to ensure logs survive restarts.
    """

    def __init__(self, base_dir: str = "/var/audit"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def append_line(self, filename: str, data: dict[str, Any]) -> None:
        """Write a line to filesystem audit file."""
        filepath = self.base_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            async with aiofiles.open(filepath, mode="a", encoding="utf-8") as f:
                await f.write(json.dumps(data, separators=(",", ":"), default=str) + "\n")
        except Exception as e:
            logger.error(
                "Failed to write audit line to filesystem",
                extra={
                    "filename": filename,
                    "error": str(e),
                }
            )
            raise

    async def read_lines(self, filename: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Read lines from filesystem audit file."""
        filepath = self.base_dir / filename
        
        if not filepath.exists():
            return []
        
        lines = []
        try:
            async with aiofiles.open(filepath, mode="r", encoding="utf-8") as f:
                async for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        lines.append(data)
                        if limit and len(lines) >= limit:
                            break
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Malformed audit line",
                            extra={"filename": filename, "error": str(e)},
                        )
        except Exception as e:
            logger.error(
                "Failed to read audit file",
                extra={"filename": filename, "error": str(e)},
            )
        
        return lines

    async def list_files(self, prefix: str = "") -> list[str]:
        """List audit files matching prefix."""
        prefix_path = self.base_dir / prefix
        
        if not prefix_path.exists():
            return []
        
        files = []
        try:
            for filepath in prefix_path.glob("**/*"):
                if filepath.is_file():
                    rel_path = filepath.relative_to(self.base_dir)
                    files.append(str(rel_path))
        except Exception as e:
            logger.error(
                "Failed to list audit files",
                extra={"prefix": prefix, "error": str(e)},
            )
        
        return sorted(files)

    async def get_file_size(self, filename: str) -> int:
        """Get audit file size in bytes."""
        filepath = self.base_dir / filename
        
        if not filepath.exists():
            return 0
        
        try:
            return filepath.stat().st_size
        except Exception as e:
            logger.error(
                "Failed to get audit file size",
                extra={"filename": filename, "error": str(e)},
            )
            return 0


class S3AuditBackend(AuditStorageBackend):
    """
    AWS S3 storage for audit files.
    
    Provides durability and availability guarantees. Requires S3 bucket
    and IAM credentials. Benefits from lifecycle policies for cost optimization.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "ledger-audit/",
        region: str = "us-east-1",
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.region = region
        self._s3_client = None

    async def _get_s3_client(self) -> Any:
        """Lazy-load S3 client (boto3 optional dependency)."""
        if self._s3_client is not None:
            return self._s3_client
        
        try:
            import aioboto3
        except ImportError:
            raise ImportError(
                "aioboto3 required for S3 audit backend. Install with: pip install aioboto3"
            )
        
        session = aioboto3.Session()
        self._s3_client = session.client("s3", region_name=self.region)
        return self._s3_client

    async def append_line(self, filename: str, data: dict[str, Any]) -> None:
        """
        Append line to S3 object.
        
        Note: This is not atomic. For high concurrency, consider batching
        or using SQS for reliable delivery.
        """
        key = f"{self.prefix}{filename}"
        line = json.dumps(data, separators=(",", ":"), default=str) + "\n"
        
        try:
            s3 = await self._get_s3_client()
            
            # For S3, we need to read-then-append since there's no append operation
            # This is a trade-off: simple but not optimal for high concurrency
            try:
                async with s3 as s3_client:
                    response = await s3_client.get_object(Bucket=self.bucket, Key=key)
                    body = await response["Body"].read()
                    existing_content = body.decode("utf-8")
                    new_content = existing_content + line
            except s3.exceptions.NoSuchKey:
                new_content = line
            
            async with s3 as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=new_content.encode("utf-8"),
                    ContentType="application/x-ndjson",
                )
            
            logger.debug(
                "Audit line written to S3",
                extra={"bucket": self.bucket, "key": key},
            )
        except Exception as e:
            logger.error(
                "Failed to write audit line to S3",
                extra={
                    "bucket": self.bucket,
                    "key": key,
                    "error": str(e),
                },
            )
            raise

    async def read_lines(self, filename: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Read lines from S3 object."""
        key = f"{self.prefix}{filename}"
        lines = []
        
        try:
            s3 = await self._get_s3_client()
            async with s3 as s3_client:
                response = await s3_client.get_object(Bucket=self.bucket, Key=key)
                body = await response["Body"].read()
                content = body.decode("utf-8")
            
            for line in content.split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    lines.append(data)
                    if limit and len(lines) >= limit:
                        break
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Malformed S3 audit line",
                        extra={"key": key, "error": str(e)},
                    )
        except Exception as e:
            logger.error(
                "Failed to read audit file from S3",
                extra={
                    "bucket": self.bucket,
                    "key": key,
                    "error": str(e),
                },
            )
        
        return lines

    async def list_files(self, prefix: str = "") -> list[str]:
        """List audit files in S3."""
        search_prefix = f"{self.prefix}{prefix}"
        files = []
        
        try:
            s3 = await self._get_s3_client()
            async with s3 as s3_client:
                paginator = s3_client.get_paginator("list_objects_v2")
                pages = paginator.paginate(Bucket=self.bucket, Prefix=search_prefix)
                
                async for page in pages:
                    if "Contents" not in page:
                        continue
                    for obj in page["Contents"]:
                        key = obj["Key"]
                        # Strip prefix for relative path
                        rel_key = key[len(self.prefix):]
                        files.append(rel_key)
        except Exception as e:
            logger.error(
                "Failed to list S3 audit files",
                extra={
                    "bucket": self.bucket,
                    "prefix": search_prefix,
                    "error": str(e),
                },
            )
        
        return sorted(files)

    async def get_file_size(self, filename: str) -> int:
        """Get S3 object size in bytes."""
        key = f"{self.prefix}{filename}"
        
        try:
            s3 = await self._get_s3_client()
            async with s3 as s3_client:
                response = await s3_client.head_object(Bucket=self.bucket, Key=key)
                return response["ContentLength"]
        except Exception as e:
            logger.error(
                "Failed to get S3 object size",
                extra={
                    "bucket": self.bucket,
                    "key": key,
                    "error": str(e),
                },
            )
            return 0


def get_audit_backend(
    backend_type: Literal["filesystem", "s3"] = "filesystem",
    **kwargs: Any,
) -> AuditStorageBackend:
    """
    Factory function for audit storage backends.
    
    Args:
        backend_type: 'filesystem' or 's3'
        **kwargs: Backend-specific configuration
        
    Returns:
        Configured AuditStorageBackend instance
        
    Example:
        # Local filesystem (default)
        backend = get_audit_backend("filesystem", base_dir="/var/audit")
        
        # AWS S3
        backend = get_audit_backend("s3", bucket="my-ledger-audit", prefix="ledger/", region="us-east-1")
    """
    if backend_type == "filesystem":
        return FilesystemAuditBackend(**kwargs)
    elif backend_type == "s3":
        return S3AuditBackend(**kwargs)
    else:
        raise ValueError(f"Unknown audit backend: {backend_type}")
