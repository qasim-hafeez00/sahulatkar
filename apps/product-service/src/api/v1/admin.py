from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from sk_shared.redis_client import RedisClient
from sk_shared.models.product import ScrapingJob, Product, Merchant

from src.core.dependencies import get_client_ip, get_current_admin_id, get_db, get_redis, require_service_token
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.merchant_repository import MerchantRepository
from src.repositories.product_repository import ProductRepository
from src.repositories.prohibited_category_repository import ProhibitedCategoryRepository
from src.repositories.scraping_job_repository import ScrapingJobRepository
from src.schemas.admin import (
    AdminCheckoutExecutionItem,
    AdminExecutionDetailResponse,
    AdminExecutionListItem,
    AdminExecutionListResponse,
    AdminExecutionRetryResponse,
    AdminProductActionResponse,
    AdminProductDetailItem,
    AdminProductDetailResponse,
    AdminProductItem,
    AdminProductListResponse,
    AdminProductPatchRequest,
    AdminScrapingJobItem,
    AdminScrapingJobsListItem,
    AdminScrapingJobsListResponse,
    DlqPurgeResponse,
    DlqReprocessResponse,
    MerchantBlockResponse,
    MerchantItem,
    MerchantListResponse,
    ProhibitedCategoryCreateRequest,
    ProhibitedCategoryDeleteResponse,
    ProhibitedCategoryItem,
    ProhibitedCategoryListResponse,
    ProhibitedCategoryUpsertResponse,
    QueueStatsResponse,
)
from src.services.audit_service import AuditService
from src.services.dlq_service import DLQService
from src.services.merchant_service import MerchantService
from src.services.product_catalog_service import ProductCatalogService
from src.services.product_extraction_service import build_upo
from src.services.product_lifecycle_service import ProductLifecycleService
from src.services.checkout.agent import CheckoutAgentService


router = APIRouter(prefix="/admin", tags=["admin"])


class ProhibitProductRequest(BaseModel):
    reason: str = "Administrative Decision"


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


@router.get("/products", response_model=AdminProductListResponse)
async def list_products(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ProductRepository(db)
    decoded_cursor = _decode_cursor(cursor)
    
    # Total count for the response
    total = await db.scalar(select(func.count(Product.id)).where(Product.deleted_at.is_(None)))

    stmt = select(Product).where(Product.deleted_at.is_(None)).order_by(desc(Product.id))
    if decoded_cursor:
        stmt = stmt.where(Product.id < decoded_cursor)
    else:
        stmt = stmt.offset(offset)
    
    rows = list(await db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = _encode_cursor(page_rows[-1].id) if has_more and page_rows else None

    items = [
        AdminProductItem(
            product_id=str(p.uuid),
            name=p.name,
            platform=p.platform,
            extraction_method=p.extraction_method,
            confidence=str(p.extraction_confidence) if p.extraction_confidence else None,
            cost_price=str(p.cost_price),
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in page_rows
    ]
    return AdminProductListResponse(items=items, total=total or 0, next_cursor=next_cursor)



@router.get("/products/{product_uuid}", response_model=AdminProductDetailResponse)
async def get_product(
    product_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    product_repo = ProductRepository(db)
    job_repo = ScrapingJobRepository(db)
    exec_repo = ExecutionRepository(db)

    product = await product_repo.find_by_uuid(product_uuid)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    jobs = await db.scalars(select(ScrapingJob).where(ScrapingJob.product_id == product.id).order_by(desc(ScrapingJob.created_at)).limit(20))
    executions = await exec_repo.list_by_product(product_id=product.id, limit=20)

    detail = AdminProductDetailItem(
        uuid=str(product.uuid),
        name=product.name,
        platform=product.platform,
        url=product.url,
        canonical_url=product.canonical_url,
        cost_price=str(product.cost_price),
        is_prohibited=product.is_prohibited,
        prohibition_reason=product.prohibition_reason,
        deleted_at=product.deleted_at.isoformat() if product.deleted_at else None,
    )

    return AdminProductDetailResponse(
        product=detail,
        scraping_jobs=[
            AdminScrapingJobItem(
                job_id=str(j.uuid),
                status=j.status,
                attempt_number=j.attempt_number,
                error_code=j.error_code,
                created_at=j.created_at.isoformat() if j.created_at else None,
            )
            for j in jobs
        ],
        checkout_executions=[
            AdminCheckoutExecutionItem(
                execution_id=str(e.uuid),
                status=e.status,
                step_reached=e.step_reached,
                merchant_order_id=e.merchant_order_id,
                created_at=e.created_at.isoformat() if e.created_at else None,
            )
            for e in executions if e.order_id and e.order_id in [j.order_id for j in jobs if j.order_id]
        ],
    )


@router.patch("/products/{product_uuid}")
async def patch_product(
    request: Request,
    product_uuid: UUID,
    payload: AdminProductPatchRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
    admin_id: int | None = Depends(get_current_admin_id),
):
    product_repo = ProductRepository(db)
    product = await product_repo.find_by_uuid(product_uuid)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    service = ProductCatalogService(db)
    old_values = {k: getattr(product, k) for k in payload.model_dump(exclude_unset=True).keys()}

    updated = await service.patch_product(product, **payload.model_dump(exclude_unset=True))

    audit = AuditService(db)
    await audit.log_action(
        admin_user_id=admin_id,
        action="patch_product",
        target_id=product.id,
        changes={"before": str(old_values), "after": str(payload.model_dump(exclude_unset=True))},
        ip_address=get_client_ip(request),
    )
    await db.commit()

    return {
        "uuid": str(updated.uuid),
        "name": updated.name,
        "url": updated.url,
        "canonical_url": updated.canonical_url,
        "cost_price": str(updated.cost_price),
        "in_stock": updated.in_stock,
    }


@router.post("/products/{product_uuid}/prohibit", response_model=AdminProductActionResponse)
async def prohibit_product(
    request: Request,
    product_uuid: UUID,
    payload: ProhibitProductRequest = Body(default_factory=ProhibitProductRequest),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
    admin_id: int | None = Depends(get_current_admin_id),
):
    repo = ProductRepository(db)
    product = await repo.find_by_uuid(product_uuid)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    service = ProductLifecycleService(db)
    await service.mark_prohibited(product, payload.reason)

    audit = AuditService(db)
    await audit.log_action(
        admin_user_id=admin_id,
        action="prohibit_product",
        target_id=product.id,
        changes={"reason": payload.reason},
        ip_address=get_client_ip(request),
    )
    await db.commit()

    return AdminProductActionResponse(status="prohibited", product_id=str(product.uuid))


@router.post("/products/{product_uuid}/unpromote")
async def unpromote_product(
    product_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ProductRepository(db)
    product = await repo.find_by_uuid(product_uuid)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    product.extraction_confidence = Decimal("0.10") # Mock unpromotion
    await db.commit()
    return {"status": "ok", "product_id": str(product.uuid)}


@router.delete("/products/{product_uuid}", response_model=AdminProductActionResponse)
async def delete_product(
    request: Request,
    product_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
    admin_id: int | None = Depends(get_current_admin_id),
):
    repo = ProductRepository(db)
    product = await repo.find_by_uuid(product_uuid)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    service = ProductLifecycleService(db)
    await service.soft_delete(product)

    audit = AuditService(db)
    await audit.log_action(
        admin_user_id=admin_id,
        action="delete_product",
        target_id=product.id,
        ip_address=get_client_ip(request),
    )
    await db.commit()

    return AdminProductActionResponse(status="deleted", product_id=str(product.uuid))


@router.get("/executions", response_model=AdminExecutionListResponse)
async def list_executions(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(None),
    product_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ExecutionRepository(db)
    decoded_cursor = _decode_cursor(cursor)
    product_filter_id: int | None = None
    if product_id is not None:
        product = await ProductRepository(db).find_by_uuid(product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")
        product_filter_id = product.id
    
    from sk_shared.models.checkout import PurchaseExecution
    if product_filter_id is None:
        total = await db.scalar(select(func.count(PurchaseExecution.id)))
    else:
        total = await db.scalar(
            select(func.count(PurchaseExecution.id))
            .join(ScrapingJob, ScrapingJob.order_id == PurchaseExecution.order_id)
            .where(ScrapingJob.product_id == product_filter_id)
        )

    stmt = select(PurchaseExecution).order_by(desc(PurchaseExecution.id))
    if product_filter_id is not None:
        stmt = stmt.join(ScrapingJob, ScrapingJob.order_id == PurchaseExecution.order_id).where(ScrapingJob.product_id == product_filter_id)
    if decoded_cursor:
        stmt = stmt.where(PurchaseExecution.id < decoded_cursor)
    else:
        stmt = stmt.offset(offset)

    rows = list(await db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = _encode_cursor(page_rows[-1].id) if has_more and page_rows else None

    items = [
        AdminExecutionListItem(
            execution_id=str(e.uuid),
            order_id=e.order_id,
            vcn_id=e.vcn_id,
            status=e.status,
            step_reached=e.step_reached,
            attempt_number=e.attempt_number,
        )
        for e in page_rows
    ]
    return AdminExecutionListResponse(items=items, total=total or 0, next_cursor=next_cursor)



@router.post("/executions/{execution_uuid}/retry", response_model=AdminExecutionRetryResponse)
async def retry_execution(
    execution_uuid: UUID,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
):
    repo = ExecutionRepository(db)
    execution = await repo.find_by_uuid(execution_uuid)
    if not execution:
        raise HTTPException(status_code=404, detail="EXECUTION_NOT_FOUND")
    
    if execution.status == "succeeded":
        raise HTTPException(status_code=409, detail="EXECUTION_ALREADY_SUCCEEDED")
    
    if execution.status == "running":
        return AdminExecutionRetryResponse(status="running", execution_id=str(execution.uuid))
    
    service = CheckoutAgentService(db, redis)
    await service.requeue_execution(execution)
    return AdminExecutionRetryResponse(status="queued", execution_id=str(execution.uuid))


@router.get("/scraping-jobs", response_model=AdminScrapingJobsListResponse)
async def list_scraping_jobs(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ScrapingJobRepository(db)
    decoded_cursor = _decode_cursor(cursor)
    
    where_clause = []
    if status is not None:
        where_clause.append(ScrapingJob.status == status)
    
    total = await db.scalar(select(func.count(ScrapingJob.id)).where(*where_clause))

    stmt = select(ScrapingJob).order_by(desc(ScrapingJob.id))
    if where_clause:
        stmt = stmt.where(*where_clause)
        
    if decoded_cursor:
        stmt = stmt.where(ScrapingJob.id < decoded_cursor)
    else:
        stmt = stmt.offset(offset)

    rows = list(await db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = _encode_cursor(page_rows[-1].id) if has_more and page_rows else None

    items = [
        AdminScrapingJobsListItem(
            job_id=str(j.uuid),
            status=j.status,
            platform=j.platform_detected,
        )
        for j in page_rows
    ]
    return AdminScrapingJobsListResponse(items=items, total=total or 0, next_cursor=next_cursor)



@router.get("/prohibited-categories", response_model=ProhibitedCategoryListResponse)
async def list_prohibited_categories(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ProhibitedCategoryRepository(db)
    rows = await repo.list_all()
    return ProhibitedCategoryListResponse(
        items=[
            ProhibitedCategoryItem(
                id=c.id,
                category_name=c.category_name,
                keywords=c.keywords or [],
                shariah_basis=c.shariah_basis,
            )
            for c in rows
        ]
    )


@router.post("/prohibited-categories", response_model=ProhibitedCategoryUpsertResponse)
async def upsert_prohibited_category(
    payload: ProhibitedCategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ProhibitedCategoryRepository(db)
    row, created = await repo.upsert(
        category_name=payload.category_name,
        keywords=payload.keywords,
        shariah_basis=payload.shariah_basis,
    )
    await db.commit()
    return ProhibitedCategoryUpsertResponse(status="created" if created else "updated", id=row.id)


@router.delete("/prohibited-categories/{cat_id}", response_model=ProhibitedCategoryDeleteResponse)
async def delete_prohibited_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = ProhibitedCategoryRepository(db)
    success = await repo.delete(cat_id)
    if not success:
        raise HTTPException(status_code=404, detail="CATEGORY_NOT_FOUND")
    await db.commit()
    return ProhibitedCategoryDeleteResponse(status="deleted", category_id=cat_id)


@router.get("/merchants", response_model=MerchantListResponse)
async def list_merchants(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = MerchantRepository(db)
    decoded_cursor = _decode_cursor(cursor)
    
    total = await db.scalar(select(func.count(Merchant.id)).where(Merchant.deleted_at.is_(None)))

    stmt = select(Merchant).where(Merchant.deleted_at.is_(None)).order_by(desc(Merchant.id))
    if decoded_cursor:
        stmt = stmt.where(Merchant.id < decoded_cursor)
    else:
        stmt = stmt.offset(offset)

    rows = list(await db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = _encode_cursor(page_rows[-1].id) if has_more and page_rows else None

    items = []
    for m in page_rows:
        count = await db.scalar(select(func.count(Product.id)).where(Product.merchant_id == m.id))
        items.append(
            MerchantItem(
                merchant_id=m.id,
                domain=m.domain,
                name=m.name,
                platform=m.platform_type,
                status=m.status,
                is_active=m.is_active,
                product_count=count or 0,
            )
        )
    return MerchantListResponse(items=items, total=total or 0, next_cursor=next_cursor)



@router.get("/merchants/{domain}")
async def get_merchant(
    domain: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    repo = MerchantRepository(db)
    merchant = await repo.find_by_domain(domain)
    if not merchant:
        raise HTTPException(status_code=404, detail="MERCHANT_NOT_FOUND")
    
    count = await db.scalar(select(func.count(Product.id)).where(Product.merchant_id == merchant.id))
    return {
        "merchant_id": merchant.id,
        "domain": merchant.domain,
        "name": merchant.name,
        "platform_type": merchant.platform_type,
        "status": merchant.status,
        "is_active": merchant.is_active,
        "product_count": count or 0,
    }


@router.post("/merchants/{domain}/block", response_model=MerchantBlockResponse)
async def block_merchant(
    request: Request,
    domain: str,
    reason: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
    admin_id: int | None = Depends(get_current_admin_id),
):
    service = MerchantService(db)
    merchant, affected = await service.block(domain, reason)

    audit = AuditService(db)
    await audit.log_action(
        admin_user_id=admin_id,
        action="block_merchant",
        target_id=merchant.id,
        changes={"domain": domain, "reason": reason, "affected_products": affected},
        ip_address=get_client_ip(request),
    )
    await db.commit()

    return MerchantBlockResponse(status="blocked", domain=domain, affected_products=affected)


_REDACTED_ENTRY_KEYS = ("pan", "cvv")


def _redact_sensitive_fields(entry: dict) -> dict:
    """Strip card data from a DLQ entry before it's ever returned by an API response.

    Defense in depth: the checkout queue payload no longer carries pan/cvv at all,
    but this guards against any stale or malformed messages already in Redis.
    """
    return {k: v for k, v in entry.items() if k not in _REDACTED_ENTRY_KEYS}


@router.get("/queue-stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
):
    service = DLQService(redis)
    stats = await service.get_stats()

    dlq_checkout = await redis.redis.lrange("sk:queue:dlq:checkout", 0, 9)
    dlq_scraping = await redis.redis.lrange("sk:queue:dlq:scraping", 0, 9)


    return QueueStatsResponse(
        checkout_queue_depth=await redis.redis.llen("sk:queue:checkout"),
        scraping_queue_depth=await redis.redis.llen("sk:queue:scraping"),
        checkout_dlq_depth=stats.get("checkout", 0),
        scraping_dlq_depth=stats.get("scraping", 0),
        checkout_dlq_entries=[_redact_sensitive_fields(json.loads(e)) for e in dlq_checkout],
        scraping_dlq_entries=[_redact_sensitive_fields(json.loads(e)) for e in dlq_scraping],
    )

@router.post("/dlq/{queue_name}/reprocess/{index}", response_model=DlqReprocessResponse)
async def reprocess_dlq_item(
    queue_name: str,
    index: int,
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
):
    service = DLQService(redis)
    try:
        item_id = await service.reprocess(queue_name, index)
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_DLQ_QUEUE")
    except IndexError:
        raise HTTPException(status_code=404, detail="ITEM_NOT_FOUND")
    
    return DlqReprocessResponse(
        status="requeued",
        item_id=item_id or "unknown",
        queue=queue_name,
        entry_index=index
    )



@router.delete("/dlq/{queue_name}/purge", response_model=DlqPurgeResponse)
async def purge_dlq(
    queue_name: str,
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
):
    service = DLQService(redis)
    try:
        count = await service.purge(queue_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_DLQ_QUEUE")
        
    return DlqPurgeResponse(purged=count, queue=queue_name)

@router.get("/analytics/extraction-stats")
async def get_extraction_stats(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    rows = await db.execute(select(ScrapingJob.status, func.count(ScrapingJob.id)).group_by(ScrapingJob.status))
    stats = [{"status": r[0], "count": r[1]} for r in rows.all()]
    return {"stats": stats}

@router.post("/prohibited-categories/sync")
async def sync_prohibited_categories(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    return {"status": "synced", "count": 0}

@router.get("/extraction-waterfall/config")
async def get_extraction_waterfall_config(
    _: None = Depends(require_service_token),
):
    return {
        "tiers": [
            {"name": "Tier 1", "type": "Violet/Rye", "timeout": 15},
            {"name": "Tier 2A", "type": "Scraper API", "timeout": 30},
            {"name": "Tier 2B", "type": "BrightData API", "timeout": 30},
            {"name": "Tier 3", "type": "Playwright Automation", "timeout": 60},
        ]
    }
