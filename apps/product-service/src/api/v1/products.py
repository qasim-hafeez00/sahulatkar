from __future__ import annotations

import base64
import json
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from sqlalchemy import select, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient
from sk_shared.models.product import Product, ScrapingJob

from src.core.dependencies import get_client_ip, get_current_user_id, get_db, get_redis, require_service_token, require_user_id
from src.repositories.product_repository import ProductRepository
from src.repositories.scraping_job_repository import ScrapingJobRepository
from src.repositories.execution_repository import ExecutionRepository
from src.schemas.products import (
    ExtractRequest,
    ExtractResponse,
    ExecutionSummary,
    JobStatusResponse,
    MultipleOffersResponse,
    OfferResponse,
    PriceHistoryResponse,
    ProductRefreshRequest,
    PriceHistoryItem,
    SearchItem,
    SearchResponse,
    SingleOfferResponse,
    ProductDetailResponse,
    ScrapingJobSummary,
    UpoResponse,
)
from src.services.product_extraction_service import ProductExtractionService, build_upo
from src.services.pricing_service import PricingService


router = APIRouter(prefix="/products", tags=["products"])


def _encode_cursor(row_id: int | str) -> str:
    payload = str(row_id)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str | None) -> int | None:
    if not cursor:
        return None
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return int(decoded)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_CURSOR")


@router.post("/extract", response_model=ExtractResponse)
async def extract_product(
    request: Request,
    request_payload: ExtractRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user_id: int | None = Depends(get_current_user_id),
):
    client_ip = get_client_ip(request)
    
    # URL Pre-validation
    from urllib.parse import urlparse
    parsed = urlparse(request_payload.raw_url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_URL_FORMAT")

    service = ProductExtractionService(db, redis)
    return await service.extract_or_enqueue(
        raw_url=request_payload.raw_url,
        user_id=current_user_id,
        client_ip=client_ip,
        order_id=request_payload.order_id,
        correlation_id=request_payload.correlation_id,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID, 
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis)
):
    service = ProductExtractionService(db, redis)
    return await service.get_job_status(job_id)


@router.get("", response_model=SearchResponse)
async def list_user_products(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(require_user_id),
):
    if current_user_id is None:
        return SearchResponse(items=[], total=0)

    decoded_cursor = _decode_cursor(cursor)
    
    # Total count for this user
    total = await db.scalar(
        select(func.count(Product.id))
        .join(ScrapingJob, Product.id == ScrapingJob.product_id)
        .where(ScrapingJob.user_id == current_user_id)
    )

    stmt = (
        select(Product)
        .join(ScrapingJob, Product.id == ScrapingJob.product_id)
        .where(ScrapingJob.user_id == current_user_id)
        .order_by(desc(Product.id))
    )
    
    if decoded_cursor:
        stmt = stmt.where(Product.id < decoded_cursor)
    else:
        stmt = stmt.offset(offset)
        
    rows = list(await db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = _encode_cursor(page_rows[-1].id) if has_more and page_rows else None
    
    items = [
        SearchItem(
            product_id=product.uuid,
            name=product.name,
            canonical_url=product.canonical_url,
            currency=product.currency,
            cost_price=Decimal(str(product.cost_price)),
            sale_price=Decimal(str(product.sale_price)) if product.sale_price is not None else None,
        )
        for product in page_rows
    ]
    return SearchResponse(items=items, total=total or 0, next_cursor=next_cursor)


@router.get("/search", response_model=SearchResponse)
async def search_products(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=20, le=100),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = ProductRepository(db)
    decoded_cursor = _decode_cursor(cursor)
    rows, total = await repo.search_paginated(query=q, limit=limit + 1, cursor_id=decoded_cursor)
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = _encode_cursor(page_rows[-1].id) if has_more and page_rows else None
    
    items = [
        SearchItem(
            product_id=product.uuid,
            name=product.name,
            canonical_url=product.canonical_url,
            currency=product.currency,
            cost_price=Decimal(str(product.cost_price)),
            sale_price=Decimal(str(product.sale_price)) if product.sale_price is not None else None,
        )
        for product in page_rows
    ]
    return SearchResponse(items=items, total=total, next_cursor=next_cursor)


@router.get("/{upo_id}", response_model=ProductDetailResponse)
async def get_product_detail(
    upo_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    service = ProductExtractionService(db, redis)
    scraping_job_repo = ScrapingJobRepository(db)
    execution_repo = ExecutionRepository(db)
    product = await service.product_repo.find_by_uuid(upo_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    jobs = await scraping_job_repo.list_by_product(product.id, limit=5)
    executions = await execution_repo.list_by_product(product.id, limit=5)

    detail = build_upo(product)
    return ProductDetailResponse(
        **detail.model_dump(),
        scraping_jobs=[ScrapingJobSummary(job_id=j.uuid, status=j.status) for j in jobs],
        checkout_executions=[ExecutionSummary(execution_id=e.uuid, status=e.status) for e in executions],
    )


@router.post("/{upo_id}/refresh")
async def refresh_product(
    upo_id: UUID,
    payload: ProductRefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
):
    service = ProductExtractionService(db, redis)
    return await service.requeue_job(upo_id, payload.reason)


@router.get("/{upo_id}/offer")
async def get_offer(
    upo_id: UUID,
    plan_months: int | None = Query(default=None),
    down_payment_pct: Decimal = Query(default=Decimal("30.0")),
    db: AsyncSession = Depends(get_db),
):
    repo = ProductRepository(db)
    product = await repo.find_by_uuid(upo_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")
        
    if not product.in_stock or product.stock_status == "out_of_stock":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OUT_OF_STOCK")

    min_dp_val = await db.scalar(text("SELECT param_value FROM system_parameters WHERE param_key = 'min_down_payment_pct'"))
    max_dp_val = await db.scalar(text("SELECT param_value FROM system_parameters WHERE param_key = 'max_down_payment_pct'"))
    min_dp = Decimal(min_dp_val) if min_dp_val else Decimal("25.0")
    max_dp = Decimal(max_dp_val) if max_dp_val else Decimal("40.0")

    if down_payment_pct < min_dp or down_payment_pct > max_dp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"INVALID_DOWN_PAYMENT_PERCENTAGE: Must be between {min_dp} and {max_dp}")

    pricing_service = PricingService()
    if plan_months is None:
        offers = pricing_service.calculate_multiple_offers(
            cost_price=Decimal(str(product.cost_price)),
            down_payment_pct=down_payment_pct,
            min_dp=min_dp,
            max_dp=max_dp,
        )
        return MultipleOffersResponse(
            product_id=product.uuid,
            upo=build_upo(product),
            financing_offers=offers,
        )
    else:
        offer = pricing_service.calculate_offer(
            cost_price=Decimal(str(product.cost_price)),
            plan_months=plan_months,
            down_payment_pct=down_payment_pct,
            min_dp=min_dp,
            max_dp=max_dp,
        )
        return SingleOfferResponse(
            product_id=product.uuid,
            upo=build_upo(product),
            plan_months=plan_months,
            financing_offer=offer,
        )


@router.get("/{upo_id}/price-history", response_model=PriceHistoryResponse)
async def get_price_history(
    upo_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ProductRepository(db)
    product = await repo.find_by_uuid(upo_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    history_rows = await repo.get_price_history(product.id)
    items = [
        PriceHistoryItem(
            old_price=Decimal(str(row["old_price"])),
            new_price=Decimal(str(row["new_price"])),
            changed_at=str(row["changed_at"]),
        )
        for row in history_rows
    ]
    return PriceHistoryResponse(product_id=product.uuid, items=items)
