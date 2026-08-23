from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.checkout import PurchaseExecution
from sk_shared.redis_client import RedisClient

from src.core.dependencies import get_db, get_redis, require_service_token
from src.schemas.products import AgentLatestExecutionResponse, AgentQueueRequest, AgentQueueResponse
from src.services.checkout import CheckoutAgentService


router = APIRouter(prefix="/products/agent", tags=["checkout-agent"])


@router.get("/order/{order_id}/latest", response_model=AgentLatestExecutionResponse)
async def get_latest_execution_for_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    """
    Looks up the most recent checkout-agent execution for an order.

    The Gateway's customer-facing agent-status proxy has only an order_id
    (from the browser) — the SSE stream endpoint below is keyed by job_id
    (the PurchaseExecution UUID), so this is the lookup step that bridges
    the two before the Gateway can start streaming.
    """
    execution = await db.scalar(
        select(PurchaseExecution)
        .where(PurchaseExecution.order_id == order_id)
        # Tie-break on id (monotonically increasing) in addition to
        # created_at — SQLite's CURRENT_TIMESTAMP is only second-precision,
        # so two executions queued within the same second would otherwise
        # sort non-deterministically.
        .order_by(PurchaseExecution.created_at.desc(), PurchaseExecution.id.desc())
        .limit(1)
    )
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EXECUTION_NOT_FOUND")
    return AgentLatestExecutionResponse(
        job_id=execution.uuid,
        status=execution.status,
        step_reached=execution.step_reached,
        merchant_order_id=execution.merchant_order_id,
    )


@router.post("/queue-job", response_model=AgentQueueResponse)
async def queue_checkout_job(
    request_payload: AgentQueueRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
):
    service = CheckoutAgentService(db, redis)
    execution = await service.queue_job(
        order_id=request_payload.order_id,
        vcn_id=request_payload.vcn_id,
        correlation_id=request_payload.correlation_id,
        force_failure=request_payload.force_failure,
    )
    return AgentQueueResponse(status="queued", job_id=execution.uuid, estimated_completion_seconds=45)


@router.get("/job/{job_id}/stream")
async def stream_job_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
) -> StreamingResponse:
    async def event_generator():
        last_step = None
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
                yield f"data: {json.dumps({'done': True})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/job/{job_id}/cancel")
async def cancel_checkout_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_service_token),
) -> dict:
    row = await db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == job_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JOB_NOT_FOUND")

    service = CheckoutAgentService(db, redis)
    await service.cancel_job(job_id)
    return {"status": "cancelled", "job_id": job_id}

@router.get("/job/{job_id}/screenshot")
async def get_checkout_screenshot(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_service_token),
):
    from fastapi.responses import RedirectResponse
    row = await db.scalar(select(PurchaseExecution).where(PurchaseExecution.uuid == job_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JOB_NOT_FOUND")

    url = row.receipt_screenshot_s3 or row.screenshot_s3
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SCREENSHOT_NOT_FOUND")
    
    return RedirectResponse(url=url)