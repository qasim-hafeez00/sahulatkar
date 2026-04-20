from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from sk_shared.constants import QueueName
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.order import Order
from sk_shared.models.product import Product, ProhibitedCategory, ScrapingJob
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_db, get_redis, require_service_token
from src.services.event_publisher import publish_event
from src.services.s3_service import S3Service


class ProhibitedCategoryCreateRequest(BaseModel):
    """Typed request model for upsert_prohibited_category.

    Using a typed Pydantic model instead of raw ``dict`` prevents
    injection of unexpected fields and provides input length validation.
    """
    category_name: str = Field(min_length=2, max_length=100)
    keywords: list[str] = Field(min_length=1)
    shariah_basis: str | None = Field(default=None, max_length=500)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_service_token)])


@router.get("/products")
async def list_products(
    platform: str | None = None,
    extraction_method: str | None = None,
    is_prohibited: bool | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    filters = [Product.deleted_at.is_(None)]
    if platform:
        filters.append(Product.platform == platform)
    if extraction_method:
        filters.append(Product.extraction_method == extraction_method)
    if is_prohibited is not None:
        filters.append(Product.is_prohibited == is_prohibited)
    if created_after:
        filters.append(Product.created_at >= created_after)
    if created_before:
        filters.append(Product.created_at <= created_before)

    total = await db.scalar(select(func.count(Product.id)).where(and_(*filters)))
    rows = await db.scalars(
        select(Product)
        .where(and_(*filters))
        .order_by(desc(Product.created_at))
        .offset(offset)
        .limit(limit)
    )
    items = [
        {
            "product_id": str(row.uuid),
            "name": row.name,
            "platform": row.platform,
            "extraction_method": row.extraction_method,
            "confidence": str(row.extraction_confidence) if row.extraction_confidence is not None else None,
            "cost_price": str(row.cost_price),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return {"items": items, "total": total or 0}


@router.get("/products/{product_id}")
async def get_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await db.scalar(select(Product).where(Product.uuid == product_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    scraping_jobs = await db.scalars(
        select(ScrapingJob).where(ScrapingJob.product_id == product.id).order_by(desc(ScrapingJob.created_at)).limit(20)
    )
    executions = await db.scalars(
        select(PurchaseExecution)
        .join(Order, Order.id == PurchaseExecution.order_id)
        .where(Order.product_id == product.id)
        .order_by(desc(PurchaseExecution.created_at))
        .limit(20)
    )

    return {
        "product": {
            "uuid": str(product.uuid),
            "name": product.name,
            "platform": product.platform,
            "url": product.url,
            "canonical_url": product.canonical_url,
            "cost_price": str(product.cost_price),
            "is_prohibited": product.is_prohibited,
            "prohibition_reason": product.prohibition_reason,
            "deleted_at": product.deleted_at.isoformat() if product.deleted_at else None,
        },
        "scraping_jobs": [
            {
                "job_id": str(job.uuid),
                "status": job.status,
                "attempt_number": job.attempt_number,
                "error_code": job.error_code,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            for job in scraping_jobs
        ],
        "checkout_executions": [
            {
                "execution_id": str(ex.uuid),
                "status": ex.status,
                "step_reached": ex.step_reached,
                "merchant_order_id": ex.merchant_order_id,
                "created_at": ex.created_at.isoformat() if ex.created_at else None,
            }
            for ex in executions
        ],
    }


@router.post("/products/{product_id}/prohibit")
async def prohibit_product(product_id: UUID, reason: str = "admin_action", db: AsyncSession = Depends(get_db), redis: RedisClient = Depends(get_redis)):
    product = await db.scalar(select(Product).where(Product.uuid == product_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")

    product.is_prohibited = True
    product.prohibition_reason = reason
    await db.commit()

    await publish_event(redis=redis, event="product.prohibited", payload={"product_id": str(product.uuid), "category": "manual", "keyword": reason})
    return {"status": "ok", "product_id": str(product.uuid)}


@router.post("/products/{product_id}/unpromote")
async def unpromote_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await db.scalar(select(Product).where(Product.uuid == product_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")
    product.is_prohibited = False
    product.prohibition_reason = None
    await db.commit()
    return {"status": "ok", "product_id": str(product.uuid)}


@router.delete("/products/{product_id}")
async def delete_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    product = await db.scalar(select(Product).where(Product.uuid == product_id, Product.deleted_at.is_(None)))
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRODUCT_NOT_FOUND")
    product.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "deleted", "product_id": str(product.uuid)}


@router.get("/executions")
async def list_executions(
    status_filter: str | None = Query(default=None, alias="status"),
    order_id: int | None = None,
    created_after: datetime | None = None,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if status_filter:
        filters.append(PurchaseExecution.status == status_filter)
    if order_id:
        filters.append(PurchaseExecution.order_id == order_id)
    if created_after:
        filters.append(PurchaseExecution.created_at >= created_after)

    where_clause = and_(*filters) if filters else True
    total = await db.scalar(select(func.count(PurchaseExecution.id)).where(where_clause))
    rows = await db.scalars(
        select(PurchaseExecution).where(where_clause).order_by(desc(PurchaseExecution.created_at)).offset(offset).limit(limit)
    )
    items = [
        {
            "execution_id": str(row.uuid),
            "order_id": row.order_id,
            "vcn_id": row.vcn_id,
            "status": row.status,
            "step_reached": row.step_reached,
            "attempt_number": row.attempt_number,
        }
        for row in rows
    ]
    return {"items": items, "total": total or 0}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: UUID, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == execution_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EXECUTION_NOT_FOUND")

    s3 = S3Service()
    screenshots = []
    for key in [row.screenshot_s3, row.receipt_screenshot_s3]:
        if key:
            screenshots.append(s3.presign_url(key))

    return {
        "execution_id": str(row.uuid),
        "order_id": row.order_id,
        "vcn_id": row.vcn_id,
        "status": row.status,
        "step_reached": row.step_reached,
        "attempt_number": row.attempt_number,
        "merchant_order_id": row.merchant_order_id,
        "failure_type": row.failure_type,
        "error_detail": row.error_detail,
        "screenshot_urls": screenshots,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "duration_ms": row.duration_ms,
    }


@router.post("/executions/{execution_id}/retry")
async def retry_execution(execution_id: UUID, db: AsyncSession = Depends(get_db), redis: RedisClient = Depends(get_redis)):
    row = await db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == execution_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EXECUTION_NOT_FOUND")

    if row.status in {"queued", "running", "pending_verification"}:
        return {"status": row.status, "execution_id": str(row.uuid)}
    if row.status == "succeeded":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EXECUTION_ALREADY_SUCCEEDED")

    row.status = "queued"
    row.step_reached = "queued"
    row.error_detail = None
    row.failure_type = None
    await db.commit()

    payload = {
        "execution_id": str(row.uuid),
        "order_id": row.order_id,
        "vcn_id": row.vcn_id,
    }
    await redis.lpush(QueueName.CHECKOUT, json.dumps(payload))
    return {"status": "queued", "execution_id": str(row.uuid)}


@router.get("/scraping-jobs")
async def list_scraping_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScrapingJob)
    if status_filter:
        stmt = stmt.where(ScrapingJob.status == status_filter)
    rows = await db.scalars(stmt.order_by(desc(ScrapingJob.created_at)).offset(offset).limit(limit))
    total_stmt = select(func.count(ScrapingJob.id))
    if status_filter:
        total_stmt = total_stmt.where(ScrapingJob.status == status_filter)
    total = await db.scalar(total_stmt)
    return {
        "items": [{"job_id": str(row.uuid), "status": row.status, "platform": row.platform_detected} for row in rows],
        "total": total or 0,
    }


@router.get("/prohibited-categories")
async def list_prohibited_categories(db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(ProhibitedCategory).order_by(ProhibitedCategory.category_name.asc()))
    return {
        "items": [
            {
                "id": row.id,
                "category_name": row.category_name,
                "keywords": row.keywords,
                "shariah_basis": row.shariah_basis,
            }
            for row in rows
        ]
    }


@router.post("/prohibited-categories")
async def upsert_prohibited_category(
    payload: ProhibitedCategoryCreateRequest,  # Typed model — not raw dict
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or merge a prohibited category.

    Keywords are merged (union) with any existing list for the same category_name.
    """
    existing = await db.scalar(
        select(ProhibitedCategory).where(ProhibitedCategory.category_name == payload.category_name)
    )
    if existing:
        existing.keywords = sorted(set((existing.keywords or []) + payload.keywords))
        if payload.shariah_basis is not None:
            existing.shariah_basis = payload.shariah_basis
        await db.commit()
        return {"status": "updated", "id": existing.id}

    row = ProhibitedCategory(
        category_name=payload.category_name,
        keywords=payload.keywords,
        shariah_basis=payload.shariah_basis,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"status": "created", "id": row.id}


@router.delete("/prohibited-categories/{category_id}")
async def delete_prohibited_category(category_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(ProhibitedCategory).where(ProhibitedCategory.id == category_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CATEGORY_NOT_FOUND")
    await db.delete(row)
    await db.commit()
    return {"status": "deleted", "category_id": category_id}


@router.get("/queue-stats")
async def get_queue_stats(redis: RedisClient = Depends(get_redis)) -> dict:
    """Return live depth of the checkout and scraping queues plus their DLQs.

    Use this endpoint to detect backpressure (checkout_queue_depth > 1000)
    or DLQ overflow (checkout_dlq_depth > 50) before manually triggering
    KEDA scale-out or HITL review.
    """
    checkout_depth = await redis.redis.llen(QueueName.CHECKOUT)
    scraping_depth = await redis.redis.llen(QueueName.SCRAPING)
    checkout_dlq = await redis.redis.llen("sk:queue:dlq:checkout")
    scraping_dlq = await redis.redis.llen("sk:queue:dlq:scraping")
    return {
        "checkout_queue_depth": checkout_depth,
        "scraping_queue_depth": scraping_depth,
        "checkout_dlq_depth": checkout_dlq,
        "scraping_dlq_depth": scraping_dlq,
    }
