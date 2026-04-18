from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import QueueName, RedisNS, RedisTTL
from sk_shared.models.product import Merchant, Product, ScrapingJob
from sk_shared.redis_client import RedisClient

from src.services.event_publisher import publish_event
from src.core.dependencies import get_current_user_id, get_db, get_redis, require_service_token
from src.schemas.products import AgentQueueRequest, AgentQueueResponse, ExtractRequest, ExtractResponse, JobStatusResponse, OfferResponse, SearchItem, SearchResponse, UpoResponse, ShippingInfo, ExtractionMeta, ExtractionPricing
from src.services.checkout_agent import CheckoutAgentService
from src.services.extraction_waterfall import ExtractionWaterfallService
from src.services.pricing_service import PricingService
from src.services.prohibited_checker import ProhibitedCheckerService
from src.services.url_normalizer import UrlNormalizerService


router = APIRouter(prefix="/products", tags=["products"])


def _url_cache_key(canonical_url: str) -> str:
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"{RedisNS.PRODUCT_URL}:{digest}"


def _build_upo(product: Product) -> UpoResponse:
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
            brand=None,
            description=None,
            images=[product.primary_image_s3] if product.primary_image_s3 else [],
        ),
        pricing=ExtractionPricing(
            amount=Decimal(str(product.cost_price)),
            currency=product.currency,
        ),
        variants=[],
        shipping=ShippingInfo(
            ships_to_pakistan=True  # Default to true, or update if schema allows
        ),
    )


@router.post("/extract", response_model=ExtractResponse)
async def extract_product(
    request_payload: ExtractRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user_id: int | None = Depends(get_current_user_id),
):
    normalizer = UrlNormalizerService()
    waterfall = ExtractionWaterfallService()
    prohibited_checker = ProhibitedCheckerService()

    try:
        normalized = await normalizer.normalize(request_payload.raw_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    url_key = _url_cache_key(normalized.canonical_url)
    cached_product_uuid = await redis.get(url_key)
    if cached_product_uuid:
        product = await db.scalar(select(Product).where(Product.uuid == UUID(cached_product_uuid), Product.deleted_at.is_(None)))
        if product is not None:
            return ExtractResponse(status="completed", upo=_build_upo(product))
        await redis.delete(url_key)

    existing_product = await db.scalar(
        select(Product)
        .where(Product.canonical_url == normalized.canonical_url, Product.deleted_at.is_(None))
        .order_by(desc(Product.created_at))
    )
    if existing_product is not None:
        await redis.set(url_key, str(existing_product.uuid), ttl=RedisTTL.PRODUCT_URL_MAP)
        return ExtractResponse(status="completed", upo=_build_upo(existing_product))

    merchant = await db.scalar(select(Merchant).where(Merchant.domain == normalized.domain))
    if merchant is None:
        merchant = Merchant(name=normalized.domain, normalized_name=normalized.domain, domain=normalized.domain, platform_type=normalized.platform)
        db.add(merchant)
        await db.flush()

    extraction_result = await waterfall.extract(normalized.canonical_url, normalized.platform)
    if extraction_result.status == "extracting":
        existing_job = await db.scalar(
            select(ScrapingJob)
            .where(
                ScrapingJob.canonical_url == normalized.canonical_url,
                ScrapingJob.status.in_(["queued", "running", "retrying"]),
            )
            .order_by(desc(ScrapingJob.created_at))
        )
        if existing_job is not None:
            return ExtractResponse(status="extracting", job_id=existing_job.uuid)

        job = ScrapingJob(
            order_id=None,
            user_id=current_user_id,
            input_url=request_payload.raw_url,
            canonical_url=normalized.canonical_url,
            platform_detected=normalized.platform,
            status="queued",
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()

        await redis.lpush(
            QueueName.SCRAPING,
            json.dumps(
                {
                    "job_id": str(job.uuid),
                    "input_url": request_payload.raw_url,
                    "canonical_url": normalized.canonical_url,
                    "platform": normalized.platform,
                    "user_id": current_user_id,
                }
            ),
        )
        await db.commit()
        return ExtractResponse(status="extracting", job_id=job.uuid)

    # GAP-16: Validation for stock and shipping
    if extraction_result.availability == "out_of_stock":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OUT_OF_STOCK")
    if getattr(extraction_result, "ships_to_pakistan", True) is False:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="DOES_NOT_SHIP_TO_PAKISTAN")

    prohibited = await prohibited_checker.check_text(
        db=db,
        text=extraction_result.title,
        raw_url=request_payload.raw_url,
        canonical_url=normalized.canonical_url,
        user_id=current_user_id,
    )
    if prohibited.is_prohibited:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PROHIBITED_CATEGORY")

    product = Product(
        merchant_id=merchant.id,
        name=extraction_result.title,
        url=request_payload.raw_url,
        canonical_url=normalized.canonical_url,
        platform=normalized.platform,
        currency="PKR",
        cost_price=extraction_result.price,
        sale_price=extraction_result.price,
        stock_status="in_stock",
        in_stock=True,
        primary_image_s3=extraction_result.image_url,
        extraction_method=extraction_result.method,
        extraction_confidence=extraction_result.confidence,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    # GAP-13: Populate search_vector (PostgreSQL only)
    if db.bind.dialect.name == "postgresql":
        await db.execute(
            text("""
                UPDATE products
                SET search_vector = to_tsvector('english', coalesce(name, '') || ' ' || coalesce(canonical_url, ''))
                WHERE id = :id
            """),
            {"id": product.id}
        )
        await db.commit()

    upo = _build_upo(product)

    # GAP-04: Publish product.extracted event
    await publish_event(
        redis=redis,
        event="product.extracted",
        payload={
            "order_id": request_payload.order_id if hasattr(request_payload, "order_id") else None,
            "product_id": str(product.uuid),
            "upo": upo.model_dump(mode="json"),
        }
    )

    cache_key = f"{RedisNS.PRODUCT_UPO}:{product.uuid}"
    await redis.set_json(cache_key, upo.model_dump(mode="json"), ttl=RedisTTL.PRODUCT_CACHE)
    await redis.set(url_key, str(product.uuid), ttl=RedisTTL.PRODUCT_URL_MAP)

    return ExtractResponse(status="completed", upo=upo)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: UUID, db: AsyncSession = Depends(get_db)):
    job = await db.scalar(select(ScrapingJob).where(ScrapingJob.uuid == job_id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JOB_NOT_FOUND")

    upo = None
    if job.product_id:
        product = await db.scalar(select(Product).where(Product.id == job.product_id))
        if product is not None:
            upo = _build_upo(product)

    return JobStatusResponse(
        job_id=job.uuid,
        status=job.status,
        upo=upo,
        error_code=job.error_code,
        error_message=job.error_message,
    )

@router.get("/search", response_model=SearchResponse)
async def search_products(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    # Full-text search using search_vector
    search_query = func.plainto_tsquery("english", q)
    where_clause = sa.and_(
        Product.search_vector.op("@@")(search_query),
        Product.deleted_at.is_(None)
    )
    
    total = await db.scalar(select(func.count(Product.id)).where(where_clause))
    rows = await db.scalars(
        select(Product)
        .where(where_clause)
        .order_by(func.ts_rank(Product.search_vector, search_query).desc())
        .limit(limit)
    )

    items = [
        SearchItem(
            product_id=product.uuid,
            name=product.name,
            canonical_url=product.canonical_url,
            currency=product.currency,
            cost_price=Decimal(str(product.cost_price)),
            sale_price=Decimal(str(product.sale_price)) if product.sale_price is not None else None,
        )
        for product in rows
    ]

    return SearchResponse(items=items, total=total or 0)


@router.get("/{upo_id}/offer", response_model=OfferResponse)
async def get_offer(
    upo_id: UUID,
    plan_months: int = Query(default=3),
    down_payment_pct: Decimal = Query(default=Decimal("30.0")),
    db: AsyncSession = Depends(get_db),
):
    product = await db.scalar(select(Product).where(Product.uuid == upo_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")
    if product.is_prohibited:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PROHIBITED_CATEGORY")
    if not product.in_stock:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OUT_OF_STOCK")

    pricing_service = PricingService()
    try:
        offer = pricing_service.calculate_offer(Decimal(str(product.cost_price)), plan_months, down_payment_pct)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return OfferResponse(
        product_id=product.uuid,
        upo=_build_upo(product),
        financing_offer=offer,
    )


@router.post("/agent/queue-job", response_model=AgentQueueResponse)
async def queue_checkout_job(
    request_payload: AgentQueueRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    service = CheckoutAgentService(db, redis)
    execution = await service.queue_job(
        order_id=request_payload.order_id,
        vcn_id=request_payload.vcn_id,
        correlation_id=request_payload.correlation_id,
        force_failure=request_payload.force_failure,
    )
    return AgentQueueResponse(status="queued", job_id=execution.uuid, estimated_completion_seconds=45)


@router.get("/agent/job/{job_id}/stream")
async def stream_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> StreamingResponse:
    from sk_shared.models.purchase import PurchaseExecution

    async def event_generator():
        last_step = None
        # Max 120 iterations x 0.5s = 60s timeout
        for _ in range(120):
            execution = await db.scalar(
                select(PurchaseExecution).where(PurchaseExecution.uuid == job_id)
            )
            if not execution:
                yield f"data: {json.dumps({'error': 'JOB_NOT_FOUND'})}\n\n"
                break

            if execution.step_reached != last_step:
                last_step = execution.step_reached
                yield f"data: {json.dumps({'step': execution.step_reached, 'status': execution.status, 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"

            if execution.status in {"succeeded", "failed", "hitl_escalated", "cancelled"}:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/agent/job/{job_id}/cancel")
async def cancel_checkout_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),  # admin/internal only
) -> dict:
    service = CheckoutAgentService(db, redis)
    await service.cancel_job(job_id)
    return {"status": "cancelled", "job_id": job_id}
