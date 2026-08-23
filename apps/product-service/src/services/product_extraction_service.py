from __future__ import annotations

import hashlib
import json
import socket
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName, RedisNS, RedisTTL
from sk_shared.models.hitl import HitlQueue
from sk_shared.models.product import Product
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.rate_limit import enforce_extract_rate_limit
from src.repositories.merchant_repository import MerchantRepository
from src.repositories.product_repository import ProductRepository
from src.repositories.scraping_job_repository import ScrapingJobRepository
from src.schemas.products import ExtractResponse, ExtractionMeta, ExtractionPricing, JobStatusResponse, ShippingInfo, UpoResponse, VariantGroup, VariantOption
from src.services.event_publisher import publish_event
from src.services.extraction_waterfall import ExtractionWaterfallService
from src.services.product_cache_service import ProductCacheService
from src.services.prohibited_checker import ProhibitedCheckerService
from src.services.s3_service import S3Service
from src.services.url_normalizer import UrlNormalizerService


def _url_cache_key(canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"{RedisNS.PRODUCT_URL}:{digest}"


def _url_lock_key(canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"{RedisNS.PRODUCT_URL}:lock:{digest}"


def _extract_images_from_product(product: Product) -> list[str]:
    images: list[str] = []
    if product.primary_image_s3:
        images.append(product.primary_image_s3)
    secondary_images = getattr(product, "secondary_images", None) or []
    for image in secondary_images:
        if image and image not in images:
            images.append(image)
    return images


def _build_variant_groups(raw_variants: list[dict] | None) -> list[VariantGroup]:
    grouped: dict[str, list[VariantOption]] = {}
    for variant in raw_variants or []:
        if not isinstance(variant, dict):
            continue
        option_name = str(variant.get("option_name") or variant.get("name") or "Option")
        value = str(variant.get("selected_value") or variant.get("value") or variant.get("label") or "")
        grouped.setdefault(option_name, []).append(
            VariantOption(
                label=value,
                value=value,
                is_available=bool(variant.get("available", True)),
            )
        )
    return [VariantGroup(option_name=option_name, options=options) for option_name, options in grouped.items()]


def _extract_image_fields(result: Any) -> tuple[str | None, list[str]]:
    images = list(getattr(result, "images", None) or [])
    primary_image = getattr(result, "image_url", None) or (images[0] if images else None)
    if primary_image and (not images or images[0] != primary_image):
        images = [primary_image, *images]
    secondary_images = images[1:] if len(images) > 1 else []
    return primary_image, secondary_images


def build_upo(product: Product) -> UpoResponse:
    return UpoResponse(
        product_id=product.uuid,
        source_url=product.canonical_url or product.url,
        platform=product.platform or "CUSTOM",
        extraction_method=product.extraction_method or "unknown",
        extraction_confidence=Decimal(str(product.extraction_confidence or "0.000")),
        availability=product.stock_status if product.stock_status in {"in_stock", "out_of_stock", "limited", "unknown"} else "unknown",
        is_purchasable=bool(product.in_stock and not product.is_prohibited),
        meta=ExtractionMeta(
            title=product.name,
            brand=getattr(product, "brand", None),
            description=getattr(product, "description", None),
            images=_extract_images_from_product(product),
        ),
        pricing=ExtractionPricing(
            amount=Decimal(str(product.cost_price)),
            currency=product.currency,
        ),
        variants=_build_variant_groups(getattr(product, "variants", None)),
        shipping=ShippingInfo(ships_to_pakistan=bool(getattr(product, "ships_to_pakistan", True))),
    )


class ProductExtractionService:
    def __init__(self, db: AsyncSession, redis: RedisClient) -> None:
        self.db = db
        self.redis = redis
        self.normalizer = UrlNormalizerService()
        self.waterfall = ExtractionWaterfallService(redis)
        self.prohibited_checker = ProhibitedCheckerService()
        self.cache_service = ProductCacheService()
        self.s3_service = S3Service()
        self.product_repo = ProductRepository(db)
        self.merchant_repo = MerchantRepository(db)
        self.scraping_job_repo = ScrapingJobRepository(db)

    async def extract_or_enqueue(
        self,
        raw_url: str,
        user_id: int | None,
        client_ip: str,
        order_id: int | None = None,
        correlation_id: str | None = None,
    ) -> ExtractResponse:
        await enforce_extract_rate_limit(
            redis=self.redis,
            user_id=user_id,
            ip=client_ip,
            limit=settings.EXTRACT_RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )

        try:
            normalized = await self.normalizer.normalize(raw_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        lock_key = _url_lock_key(normalized.canonical_url)
        lock_acquired = await self.redis.redis.set(
            lock_key,
            socket.gethostname(),
            ex=settings.EXTRACTION_TIMEOUT_SECONDS + 10,
            nx=True,
        )
        if not lock_acquired:
            # Another request is processing this URL; return existing product/job if present.
            existing_product = await self.product_repo.find_by_canonical_url(normalized.canonical_url)
            if existing_product is not None:
                return ExtractResponse(status="completed", upo=build_upo(existing_product), meta={"cache_hit": False})
            existing_job = await self.scraping_job_repo.find_active_by_canonical_url(normalized.canonical_url)
            if existing_job is not None:
                return ExtractResponse(status="extracting", job_id=existing_job.uuid)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EXTRACTION_IN_PROGRESS")

        try:
            url_key = _url_cache_key(normalized.canonical_url)
            cached_product = await self.cache_service.get_by_url(self.redis, self.db, normalized.canonical_url)
            if cached_product is not None:
                return ExtractResponse(status="completed", upo=build_upo(cached_product), meta={"cache_hit": True})

            existing_product = await self.product_repo.find_by_canonical_url(normalized.canonical_url)
            if existing_product is not None:
                await self.redis.set(url_key, str(existing_product.uuid), ttl=RedisTTL.PRODUCT_URL_MAP)
                return ExtractResponse(status="completed", upo=build_upo(existing_product), meta={"cache_hit": False})

            merchant, _ = await self.merchant_repo.get_or_create(normalized.domain, normalized.platform)

            extraction_result = await self.waterfall.extract(
                normalized.canonical_url, normalized.platform, scrape_config=merchant.scrape_config
            )
            if extraction_result.status == "extracting":
                existing_job = await self.scraping_job_repo.find_active_by_canonical_url(normalized.canonical_url)
                if existing_job is not None:
                    return ExtractResponse(status="extracting", job_id=existing_job.uuid)

                job = await self.scraping_job_repo.create_queued(
                    order_id=order_id,
                    user_id=user_id,
                    input_url=raw_url,
                    canonical_url=normalized.canonical_url,
                    platform_detected=normalized.platform,
                )

                await self.redis.lpush(
                    QueueName.SCRAPING,
                    json.dumps(
                        {
                            "job_id": str(job.uuid),
                            "input_url": raw_url,
                            "canonical_url": normalized.canonical_url,
                            "platform": normalized.platform,
                            "user_id": user_id,
                            "order_id": order_id,
                            "correlation_id": correlation_id,
                        }
                    ),
                )
                await self.db.commit()
                return ExtractResponse(status="extracting", job_id=job.uuid)

            if extraction_result.status == "hitl_required":
                return ExtractResponse(status="extracting", meta={"hitl_required": True})

            if extraction_result.availability == "out_of_stock":
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OUT_OF_STOCK")
            if getattr(extraction_result, "ships_to_pakistan", True) is False:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="DOES_NOT_SHIP_TO_PAKISTAN")

            prohibited = await self.prohibited_checker.check_text(
                db=self.db,
                text=extraction_result.title,
                raw_url=raw_url,
                canonical_url=normalized.canonical_url,
                redis=self.redis,
                user_id=user_id,
            )

            if prohibited.is_prohibited:
                if settings.FEATURE_HITL_ESCALATION:
                    hitl = HitlQueue(
                        order_id=order_id, # Now nullable in HitlQueue model
                        execution_id=None,
                        status="pending",
                        priority=2, # Higher priority for policy violations
                        failure_reason=f"PROHIBITED_CATEGORY: {prohibited.category or 'unknown'} (Keyword: {prohibited.keyword})",
                    )
                    self.db.add(hitl)
                await self.db.commit()
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PROHIBITED_CATEGORY")


            primary_image_s3, secondary_images = _extract_image_fields(extraction_result)
            product_payload = {
                "merchant_id": merchant.id,
                "name": extraction_result.title,
                "url": raw_url,
                "canonical_url": normalized.canonical_url,
                "platform": normalized.platform,
                "currency": "PKR",
                "cost_price": extraction_result.price,
                "sale_price": extraction_result.price,
                "stock_status": "in_stock",
                "in_stock": True,
                "primary_image_s3": primary_image_s3,
                "secondary_images": secondary_images,
                "shariah_category": prohibited.category if not prohibited.is_prohibited else None,
                "brand": getattr(extraction_result, "brand", None),
                "description": getattr(extraction_result, "description", None),
                "ships_to_pakistan": bool(getattr(extraction_result, "ships_to_pakistan", True)),
                "variants": list(getattr(extraction_result, "variants", None) or []),
                "status": "active",
                "extraction_method": extraction_result.method,
                "extraction_confidence": extraction_result.confidence,
            }
            product, _ = await self.product_repo.upsert_by_canonical_url(normalized.canonical_url, product_payload)
            await self.db.commit()
            await self.db.refresh(product)

            if product.primary_image_s3 and product.primary_image_s3.startswith("http") and settings.IMAGE_CACHE_ENABLED:
                import asyncio
                import logging
                logger = logging.getLogger(__name__)
                for attempt in range(3):
                    try:
                        cached_key = await self.s3_service.cache_product_image(product.primary_image_s3, str(product.uuid))
                        if cached_key:
                            product.primary_image_s3 = cached_key
                            await self.db.commit()
                        break
                    except Exception as e:
                        if attempt == 2:
                            logger.error(f"ALERT: S3 Image Caching failed after 3 attempts for product {product.uuid}: {e}", exc_info=True)
                        else:
                            await asyncio.sleep(2)

            if settings.DATABASE_DIALECT == "postgresql":
                await self.db.execute(
                    text(
                        """
                        UPDATE products
                        SET search_vector = to_tsvector('english', coalesce(name, '') || ' ' || coalesce(canonical_url, ''))
                        WHERE id = :id
                        """
                    ),
                    {"id": product.id},
                )
                await self.db.commit()

            upo = build_upo(product)
            await publish_event(
                redis=self.redis,
                event="product.extracted",
                payload={
                    "order_id": order_id,
                    "correlation_id": correlation_id,
                    "product_id": str(product.uuid),
                    "upo": upo.model_dump(mode="json"),
                },
            )
            await self.cache_service.set_upo(self.redis, str(product.uuid), upo.model_dump(mode="json"))
            await self.cache_service.set_by_url(self.redis, normalized.canonical_url, str(product.uuid))

            return ExtractResponse(status="completed", upo=upo, meta={"cache_hit": False})
        finally:
            await self.redis.redis.delete(lock_key)

    async def get_job_status(self, job_id: UUID, current_user_id: int) -> JobStatusResponse:
        job = await self.scraping_job_repo.find_by_uuid(job_id)
        # Return 404 (not 403) for jobs owned by someone else, or jobs with no
        # owner at all, so an authenticated caller can't distinguish "this
        # job doesn't exist" from "this job exists but isn't yours" and use
        # that to enumerate other users' job ids.
        if job is None or job.user_id != current_user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JOB_NOT_FOUND")

        upo = None
        if job.product_id:
            product = await self.product_repo.find_by_id(job.product_id)
            if product:
                upo = build_upo(product)

        return JobStatusResponse(
            job_id=job.uuid,
            status=job.status,
            upo=upo,
            error_code=job.error_code,
            error_message=job.error_message,
        )

    async def requeue_job(self, upo_id: UUID, reason: str) -> dict[str, Any]:
        product = await self.product_repo.find_by_uuid(upo_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

        existing_job = await self.scraping_job_repo.find_active_by_product_id(product.id)
        if existing_job is not None:
            return {"status": "queued", "job_id": str(existing_job.uuid), "reason": reason}

        await self.cache_service.invalidate(self.redis, str(product.uuid), product.canonical_url or product.url)

        job = await self.scraping_job_repo.create_queued(
            order_id=None,
            user_id=None,
            input_url=product.url,
            canonical_url=product.canonical_url,
            platform_detected=product.platform or "CUSTOM",
        )
        job.product_id = product.id
        
        # Reset extraction confidence so it's fresh
        product.extraction_method = None
        product.extraction_confidence = None
        await self.db.commit()

        await self.redis.lpush(
            QueueName.SCRAPING,
            json.dumps(
                {
                    "job_id": str(job.uuid),
                    "input_url": product.url,
                    "canonical_url": product.canonical_url or product.url,
                    "platform": product.platform or "CUSTOM",
                }
            ),
        )
        return {"status": "queued", "job_id": str(job.uuid), "reason": reason}
