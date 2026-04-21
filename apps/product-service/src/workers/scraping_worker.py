from __future__ import annotations

import asyncio
import json
import signal
import socket
from datetime import datetime, timedelta, timezone
from uuid import UUID

from opentelemetry import trace
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName, RedisNS, RedisTTL
from sk_shared.database import SessionLocal
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.product import Merchant, Product, ScrapingJob
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.distributed_lock import DistributedLock
from src.repositories.merchant_repository import MerchantRepository
from src.repositories.product_repository import ProductRepository
from src.services.event_publisher import publish_event
from src.services.extraction_waterfall import ExtractionWaterfallService
from src.services.product_cache_service import ProductCacheService
from src.services.product_extraction_service import build_upo
from src.services.s3_service import S3Service


def _extract_image_fields(result: object) -> tuple[str | None, list[str]]:
    images = list(getattr(result, "images", None) or [])
    primary_image = getattr(result, "image_url", None) or (images[0] if images else None)
    if primary_image and (not images or images[0] != primary_image):
        images = [primary_image, *images]
    secondary_images = images[1:] if len(images) > 1 else []
    return primary_image, secondary_images


tracer = trace.get_tracer("product-service.worker.scraping")


class ScrapingWorker:
    def __init__(self, redis: RedisClient, max_concurrency: int = 5) -> None:
        self.redis = redis
        self.running = True
        self._sem = asyncio.Semaphore(max_concurrency)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: setattr(self, "running", False))
        except NotImplementedError:
            # Signal handlers not supported on this platform/event loop
            pass

        while self.running:
            # GAP-01: FIFO - brpop pops from RIGHT. Producer lpush to LEFT. Correct.
            job = await self.redis.redis.brpop(QueueName.SCRAPING, timeout=5)
            if job is None:
                continue

            try:
                payload = json.loads(job[1].decode("utf-8"))
                # Tasking to semaphore for concurrency
                asyncio.create_task(self._process_with_sem(payload))
            except Exception as e:
                # GAP-12: Send to DLQ
                await self._send_to_dlq({"raw_data": job[1].decode("utf-8")}, str(e))

    async def _process_with_sem(self, payload: dict) -> None:
        async with self._sem:
            with tracer.start_as_current_span(
                "scraping_worker.process",
                attributes={
                    "job_id": str(payload.get("job_id", "")),
                    "correlation_id": str(payload.get("correlation_id", "")),
                },
            ):
                try:
                    # Fresh session for each worker task
                    async with SessionLocal() as db:
                        await self._process(payload, db)
                except Exception as e:
                    await self._send_to_dlq(payload, str(e))

    async def _send_to_dlq(self, payload: dict, error: str) -> None:
        dlq_entry = {
            **payload,
            "dlq_error": error,
            "dlq_at": datetime.now(timezone.utc).isoformat(),
            "worker": socket.gethostname(),
        }
        # GAP-A FIX: Use short queue name to avoid doubled prefix
        # (was: sk:queue:dlq:sk:queue:scraping — now: sk:queue:dlq:scraping)
        await self.redis.lpush("sk:queue:dlq:scraping", json.dumps(dlq_entry))

    async def _process(self, payload: dict, db: AsyncSession) -> None:
        merchant_repo = MerchantRepository(db)
        product_repo = ProductRepository(db)

        job_id = payload.get("job_id")
        if not job_id:
            raise ValueError("No job_id in payload")
        try:
            job_uuid = UUID(str(job_id))
        except Exception as exc:
            raise ValueError(f"Invalid job_id UUID: {job_id}") from exc

        scraping_job = await db.scalar(select(ScrapingJob).where(ScrapingJob.uuid == job_uuid))
        if scraping_job is None:
            return
        if scraping_job.status in {"completed", "failed"}:
            return

        async with DistributedLock(self.redis, f"scraping:{normalized_url}", timeout=120):
            scraping_job.status = "running"
            scraping_job.started_at = datetime.now(timezone.utc)
            await db.flush()

        service = ExtractionWaterfallService(self.redis)
        # DESIGN-03 FIX: Call extract() (full waterfall: Tier1→Tier2A→Tier2B→Tier3)
        # instead of run_tier3() directly, so fast-path APIs (Rye, Violet) are used
        # for supported platforms, reducing unnecessary Playwright sessions.
        result = await service.extract(payload["canonical_url"], payload.get("platform", "CUSTOM"))
        if result.status != "completed":
            scraping_job.error_code = result.error_code
            scraping_job.error_message = result.error_message
            scraping_job.completed_at = datetime.now(timezone.utc)

            max_attempts = scraping_job.max_attempts or settings.EXTRACTION_MAX_RETRIES
            if scraping_job.attempt_number < max_attempts:
                scraping_job.attempt_number += 1
                scraping_job.status = "retrying"
                await db.commit()
                # GAP-01: Re-queue at the front (FIFO) or back? 
                # FIFO means lpush to left. Correct.
                retry_payload = dict(payload)
                retry_payload["job_id"] = str(job_uuid)
                await self.redis.lpush(QueueName.SCRAPING, json.dumps(retry_payload))
                return

            scraping_job.status = "failed"
            scraping_job.error_code = result.error_code
            scraping_job.error_message = result.error_message
            
            # GAP-11: HITL Escalation for Scraper
            if settings.FEATURE_HITL_ESCALATION and scraping_job.order_id:
                hitl = HitlQueue(
                    order_id=scraping_job.order_id,
                    priority=3,
                    status="pending",
                    failure_reason=f"Scraping failed after {scraping_job.max_attempts} attempts: {result.error_message}",
                    sla_deadline=datetime.now(timezone.utc) + timedelta(minutes=settings.HITL_SLA_MINUTES),
                )
                db.add(hitl)

            await db.commit()

            await publish_event(
                redis=self.redis,
                event="product.extraction_failed",
                payload={
                    "order_id": scraping_job.order_id,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                },
            )
            return

        if getattr(result, "ships_to_pakistan", True) is False:
            scraping_job.status = "failed"
            scraping_job.error_code = "DOES_NOT_SHIP_TO_PAKISTAN"
            scraping_job.error_message = "Extracted product does not ship to Pakistan"
            scraping_job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await publish_event(
                redis=self.redis,
                event="product.extraction_failed",
                payload={
                    "order_id": scraping_job.order_id,
                    "error_code": scraping_job.error_code,
                    "error_message": scraping_job.error_message,
                },
            )
            return

        canonical_url = payload["canonical_url"]
        domain = canonical_url.split("//", 1)[-1].split("/", 1)[0].lower().replace("www.", "")
        merchant, _ = await merchant_repo.get_or_create(domain, payload.get("platform", "CUSTOM"))

        primary_image_s3, secondary_images = _extract_image_fields(result)
        product_payload = {
            "merchant_id": merchant.id,
            "name": result.title,
            "url": payload["input_url"],
            "canonical_url": payload["canonical_url"],
            "platform": payload.get("platform", "CUSTOM"),
            "currency": "PKR",
            "cost_price": result.price,
            "sale_price": result.price,
            "stock_status": "in_stock",
            "in_stock": True,
            "primary_image_s3": primary_image_s3,
            "secondary_images": secondary_images,
            "shariah_category": prohibited_check.category if not prohibited_check.is_prohibited else None,
            "brand": getattr(result, "brand", None),
            "description": getattr(result, "description", None),
            "ships_to_pakistan": bool(getattr(result, "ships_to_pakistan", True)),
            "variants": list(getattr(result, "variants", None) or []),
            "status": "active",
            "extraction_method": result.method,
            "extraction_confidence": result.confidence,
        }
        product, _ = await product_repo.upsert_by_canonical_url(payload["canonical_url"], product_payload)

        # GAP-B FIX: Check dialect via settings flag; avoids deprecated session.bind
        # attribute that is removed in some SQLAlchemy 2.x async configurations.
        if settings.DATABASE_DIALECT == "postgresql":
            await db.execute(
                text("""
                    UPDATE products
                    SET search_vector = to_tsvector('english', coalesce(name, '') || ' ' || coalesce(canonical_url, ''))
                    WHERE id = :id
                """),
                {"id": product.id}
            )

        if product.primary_image_s3 and product.primary_image_s3.startswith("http") and settings.IMAGE_CACHE_ENABLED:
            try:
                cached_key = await S3Service().cache_product_image(product.primary_image_s3, str(product.uuid))
                if cached_key:
                    product.primary_image_s3 = cached_key
                    await db.commit()
                    await db.refresh(product)
            except Exception:
                pass

        scraping_job.product_id = product.id
        scraping_job.status = "completed"
        scraping_job.result = {
            "product_uuid": str(product.uuid),
            "title": result.title,
            "price": str(result.price),
            "method": result.method,
            "confidence": str(result.confidence),
        }
        scraping_job.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # GAP-04: product.extracted event
        await publish_event(
            redis=self.redis,
            event="product.extracted",
            payload={
                "order_id": scraping_job.order_id,
                "product_id": str(product.uuid),
                "title": product.name,
                "price": str(product.cost_price),
                "is_async": True,
            }
        )
        cache_service = ProductCacheService()
        upo = build_upo(product)
        await cache_service.set_upo(self.redis, str(product.uuid), upo.model_dump(mode="json"))
        await cache_service.set_by_url(self.redis, product.canonical_url or product.url, str(product.uuid))


# ---------------------------------------------------------------------------
# BUG-04 FIX: Standalone entry-point functions required by pyproject.toml
#   scraping-worker = "src.workers.scraping_worker:main"
# ---------------------------------------------------------------------------
import logging as _logging  # noqa: E402 (avoid top-level collision with sk_shared)


async def _amain() -> None:
    from sk_shared.redis_client import get_redis_client

    _logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
    worker = ScrapingWorker(redis, max_concurrency=5)
    try:
        await worker.run()
    finally:
        await redis.close()
        _logging.getLogger(__name__).info("ScrapingWorker shut down cleanly")


def main() -> None:  # noqa: D401
    """Entry point declared in pyproject.toml as ``scraping-worker``."""
    asyncio.run(_amain())
