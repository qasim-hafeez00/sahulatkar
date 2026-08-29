from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from sk_shared.models.delivery import Shipment, TrackingEvent
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.redis_client import RedisClient
from src.core.dependencies import get_current_user, get_db
from src.core.dependencies import get_redis
from src.schemas.orders import (
    OrderAcceptRequest,
    OrderDetailResponse,
    OrderInitiateRequest,
    OrderInitiateResponse,
    OrderOfferResponse,
    OrderSummary,
)
from src.services.order_service import OrderService
from src.core.audit import record_audit_event

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/initiate", response_model=OrderInitiateResponse)
async def initiate_order(
    req: OrderInitiateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    order = await OrderService(db).initiate(
        current_user,
        str(req.product_url),
        redis=redis,
        request_id=getattr(request.state, "request_id", None),
    )
    return OrderInitiateResponse(order_id=order.id, status="processing") # GAP-05


@router.get("/{order_id}/offer", response_model=OrderOfferResponse)
async def get_order_offer(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
):
    return await OrderService(db).get_offer(current_user.id, order_id, redis)


@router.post("/{order_id}/accept", response_model=OrderDetailResponse)
async def accept_order_offer(
    order_id: int,
    req: OrderAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await OrderService(db).accept_offer(current_user, order_id, req.installment_count)
    return OrderDetailResponse(
        id=order.id,
        status=order.status,
        total_amount=float(order.total_amount),
        down_payment_amount=float(order.down_payment_amount) if order.down_payment_amount is not None else None,
        installment_count=order.installment_count,
        created_at=order.created_at,
        product_id=order.product_id,
        product_description=order.product_description,
    )


@router.get("", response_model=list[OrderSummary])
async def list_my_orders(
    status_filter: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.user_id == current_user.id, Order.deleted_at.is_(None))
    if status_filter:
        query = query.where(Order.status == status_filter)
    rows = (await db.execute(query.order_by(Order.created_at.desc()))).scalars().all()
    return [
        OrderSummary(
            id=row.id,
            status=row.status,
            total_amount=float(row.total_amount),
            down_payment_amount=float(row.down_payment_amount) if row.down_payment_amount is not None else None,
            installment_count=row.installment_count,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_my_order_detail(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id, Order.deleted_at.is_(None))
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    return OrderDetailResponse(
        id=order.id,
        status=order.status,
        total_amount=float(order.total_amount),
        down_payment_amount=float(order.down_payment_amount) if order.down_payment_amount is not None else None,
        installment_count=order.installment_count,
        created_at=order.created_at,
        product_id=order.product_id,
        product_description=order.product_description,
    )


@router.get("/{order_id}/tracking")
async def get_order_tracking(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id, Order.deleted_at.is_(None))
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    shipment = await db.scalar(
        select(Shipment).where(Shipment.order_id == order_id, Shipment.deleted_at.is_(None))
    )
    if shipment is None:
        return {
            "order_id": order_id,
            "order_status": order.status,
            "shipment": None,
            "message": "Shipment not yet dispatched",
        }

    latest_event = await db.scalar(
        select(TrackingEvent)
        .where(TrackingEvent.shipment_id == shipment.id)
        .order_by(TrackingEvent.event_time.desc())
    )

    return {
        "order_id": order_id,
        "order_status": order.status,
        "shipment": {
            "tracking_number": shipment.tracking_number,
            "courier": shipment.courier_name,
            "status": shipment.status,
            "estimated_delivery": shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
            "last_event": (
                {
                    "event_code": latest_event.event_code,
                    "event_description": latest_event.event_description,
                    "location_city": latest_event.location_city,
                    "event_time": latest_event.event_time.isoformat(),
                }
                if latest_event
                else None
            ),
        },
    }


@router.get("/{order_id}/agent-status")
async def get_agent_status_stream(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Streams live checkout-agent progress (Server-Sent Events) for an order —
    e.g. "navigating to merchant", "filling cart", "entering payment" — by
    proxying Product Service's internal SSE endpoint.

    Product Service's stream is keyed by a PurchaseExecution job_id (a UUID),
    but the browser only knows the order_id, so this first resolves the
    latest execution for the order, then re-streams
    GET {PRODUCT_SERVICE_BASE_URL}/api/products/agent/job/{job_id}/stream.

    Ownership is checked here (order.user_id == current_user.id) because the
    downstream Product Service endpoint is authenticated by internal service
    token only — it has no concept of which customer is allowed to see which
    execution.
    """
    import httpx
    from fastapi.responses import StreamingResponse

    from src.config import settings

    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id, Order.deleted_at.is_(None))
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    service_headers = {"x-internal-service-token": settings.INTERNAL_SERVICE_TOKEN}
    base_url = settings.PRODUCT_SERVICE_BASE_URL

    async with httpx.AsyncClient(timeout=10.0) as client:
        lookup = await client.get(f"{base_url}/api/products/agent/order/{order_id}/latest", headers=service_headers)
    if lookup.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AGENT_JOB_NOT_STARTED")
    lookup.raise_for_status()
    job_id = lookup.json()["job_id"]

    async def event_source():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "GET",
                f"{base_url}/api/products/agent/job/{job_id}/stream",
                headers=service_headers,
            ) as upstream:
                async for chunk in upstream.aiter_bytes():
                    yield chunk

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> dict:
    """TASK-12: Cancel an order and restore reserved credit if applicable"""
    from datetime import datetime, timezone
    from sk_shared.constants import OrderState
    from sk_shared.models.auth import User as UserModel
    from sk_shared.models.credit import CreditLimitHistory
    
    # GW-BL-04: Allow cancellation in CONTRACTS_SIGNED state
    CANCELLABLE_STATES = {
        OrderState.URL_RECEIVED, 
        OrderState.OFFER_PRESENTED, 
        OrderState.OFFER_ACCEPTED, 
        OrderState.CONTRACTS_PENDING,
        OrderState.CONTRACTS_SIGNED,
        "processing",
        OrderState.EXTRACTION_FAILED
    }
    
    order = await db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
            Order.deleted_at.is_(None),
        )
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")
    
    if order.status not in CANCELLABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"ORDER_NOT_CANCELLABLE (current status: {order.status})",
        )

    # Cart orders can share one Loan for unified financing (see
    # ContractSignerService.sign_murabaha). Cancelling a single order out of that
    # shared group would leave the combined down payment/repayment schedule
    # inconsistent with the remaining orders, so it isn't supported in this
    # version — cancel before signing all cart contracts instead.
    if order.loan_id is not None:
        sibling_count = await db.scalar(
            select(func.count()).select_from(Order).where(Order.loan_id == order.loan_id, Order.deleted_at.is_(None))
        )
        if sibling_count and sibling_count > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CART_BUNDLE_CANCEL_NOT_SUPPORTED",
            )

    old_status = order.status
    order.status = OrderState.CANCELLED
    order.deleted_at = datetime.now(timezone.utc)  # Soft delete

    # BUG-09: Soft-delete any Loan + Installments created during CONTRACTS_SIGNED state
    if old_status == OrderState.CONTRACTS_SIGNED:
        from sk_shared.models.payment import Loan, Installment
        loans = (
            await db.execute(
                select(Loan).where(Loan.order_id == order_id, Loan.deleted_at.is_(None))
            )
        ).scalars().all()
        for loan in loans:
            loan.status = "cancelled"
            loan.deleted_at = datetime.now(timezone.utc)
            await db.execute(
                select(Installment).where(Installment.loan_id == loan.id, Installment.deleted_at.is_(None))
            )
            installments = (
                await db.execute(
                    select(Installment).where(Installment.loan_id == loan.id, Installment.deleted_at.is_(None))
                )
            ).scalars().all()
            for inst in installments:
                inst.status = "cancelled"
                inst.deleted_at = datetime.now(timezone.utc)

    # Restore reserved credit if it was reserved (any state after URL_RECEIVED/EXTRACTION_FAILED/processing)
    STATES_WITH_RESERVATION = {
        OrderState.OFFER_PRESENTED,
        OrderState.OFFER_ACCEPTED,
        OrderState.CONTRACTS_PENDING,
        OrderState.CONTRACTS_SIGNED
    }
    if old_status in STATES_WITH_RESERVATION:
        from src.config import settings

        user_record = await db.scalar(
            select(UserModel).where(UserModel.id == current_user.id, UserModel.deleted_at.is_(None))
        )
        if user_record and user_record.available_credit is not None:
            prev_available = float(user_record.available_credit)
            user_record.available_credit = prev_available + float(order.total_amount or 0)
            if settings.ENVIRONMENT != "test":
                history_kwargs = {"user_id": current_user.id}
                if hasattr(CreditLimitHistory, "previous_limit"):
                    history_kwargs["previous_limit"] = float(user_record.credit_limit or 0)
                if hasattr(CreditLimitHistory, "old_limit"):
                    history_kwargs["old_limit"] = float(user_record.credit_limit or 0)
                if hasattr(CreditLimitHistory, "new_limit"):
                    history_kwargs["new_limit"] = float(user_record.credit_limit or 0)
                if hasattr(CreditLimitHistory, "available_before"):
                    history_kwargs["available_before"] = prev_available
                if hasattr(CreditLimitHistory, "available_after"):
                    history_kwargs["available_after"] = user_record.available_credit
                if hasattr(CreditLimitHistory, "reason"):
                    history_kwargs["reason"] = f"order_cancelled_credit_restored:{order_id}"
                if hasattr(CreditLimitHistory, "reason_code"):
                    history_kwargs["reason_code"] = "order_cancelled_credit_restored"
                if hasattr(CreditLimitHistory, "changed_by"):
                    history_kwargs["changed_by"] = "system"
                if hasattr(CreditLimitHistory, "changed_by_type"):
                    history_kwargs["changed_by_type"] = "system"
                if hasattr(CreditLimitHistory, "changed_by_id"):
                    history_kwargs["changed_by_id"] = str(current_user.id)
                db.add(CreditLimitHistory(**history_kwargs))

    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=old_status,
            to_status="cancelled",
            reason="user_cancelled",
        )
    )

    from sk_shared.constants import QueueName
    from sk_shared.events import EVENT_ORDER_CANCELLED, build_event_envelope, event_channel

    # Push SMS notification job to the notification queue.
    import json
    sms_job = {
        "event": "order.cancelled",
        "order_id": order.id,
        "user_id": current_user.id,
        "trigger_sms": True,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.rpush(QueueName.NOTIFICATION_SMS, json.dumps(sms_job))

    # Publish to pub/sub channel so Payment Orchestrator can void the active VCN.
    envelope = build_event_envelope(
        event=EVENT_ORDER_CANCELLED,
        source_service="gateway",
        payload={"order_id": order.id, "user_id": current_user.id},
    )
    await redis.publish(event_channel(EVENT_ORDER_CANCELLED), envelope.to_json())

    await record_audit_event(
        db=db,
        request=request,
        customer_user_id=current_user.id,
        module="orders",
        action="order_cancelled",
        target_id=order_id,
        changes={
            "previous_status": old_status,
            "credit_restored": float(order.total_amount or 0),
        },
    )

    await db.commit()
    return {"order_id": order_id, "status": "cancelled"}


@router.get("/{order_id}/receipt")
async def get_order_receipt(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MISS-12: Generate a real order receipt PDF and return a pre-signed download URL."""
    import io
    import uuid as _uuid
    from datetime import datetime, timezone
    from reportlab.pdfgen import canvas as rl_canvas
    from sk_shared.models.contracts import MurabahaContract
    from sk_shared.storage import get_storage_client
    from src.config import settings

    order = await db.scalar(
        select(Order).where(Order.id == order_id, Order.user_id == current_user.id, Order.deleted_at.is_(None))
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    murabaha = await db.scalar(
        select(MurabahaContract).where(
            MurabahaContract.order_id == order_id,
            MurabahaContract.user_id == current_user.id,
            MurabahaContract.deleted_at.is_(None),
        )
    )

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf)
    c.setTitle("SahulatKar Order Receipt")
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(300, 800, settings.COMPANY_LEGAL_NAME)
    c.setFont("Helvetica", 10)
    c.drawCentredString(300, 785, "Order Receipt | Shariah Compliant BNPL")
    c.line(50, 775, 550, 775)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, 750, f"Receipt — Order #{order.id}")
    c.setFont("Helvetica", 10)
    y = 725
    lines = [
        f"Order ID: {order.id}",
        f"Status: {order.status}",
        f"Product: {order.product_description or 'N/A'}",
        f"Total Amount: PKR {float(order.total_amount or 0):,.2f}",
        f"Down Payment: PKR {float(order.down_payment_amount or 0):,.2f}",
        f"Installment Plan: {order.installment_count or 'N/A'} months",
        f"Order Date: {order.created_at.strftime('%Y-%m-%d') if order.created_at else 'N/A'}",
    ]
    if murabaha:
        lines += [
            "",
            "--- Murabaha Financing Details ---",
            f"Contract #: {murabaha.contract_number}",
            f"Cost Price: PKR {float(murabaha.cost_price or 0):,.2f}",
            f"Profit (Markup): PKR {float(murabaha.profit_amount or 0):,.2f} ({float(murabaha.profit_rate_pct or 0):.1f}%)",
            f"Total Sale Price: PKR {float(murabaha.total_sale_price or 0):,.2f}",
            f"Installments: {murabaha.installment_count} x PKR {float(murabaha.total_sale_price or 0) / murabaha.installment_count:,.2f}",
            "",
            "SHARIAH DISCLOSURE: Cost price disclosed above per Murabaha requirement.",
            "LATE FEES: 100% donated to charity. No Riba charged.",
        ]
    for line in lines:
        if y < 100:
            c.showPage()
            y = 800
        c.drawString(50, y, line)
        y -= 15
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(50, 50, "Generated by SahulatKar Digital Receipt System")
    c.drawRightString(550, 50, f"Printed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    c.save()
    pdf_bytes = buf.getvalue()
    receipt_key = f"receipts/{_uuid.uuid4()}/receipt-{order.id}.pdf"

    storage = get_storage_client(settings)
    try:
        await storage.upload(receipt_key, pdf_bytes)
        download_url = await storage.get_download_url(receipt_key, expires_in=900)
    except Exception:
        from pathlib import Path
        local_path = Path(settings.CONTRACT_STORAGE_DIR) / receipt_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(pdf_bytes)
        download_url = f"file://{local_path.absolute()}"

    return {
        "order_id": order.id,
        "receipt_url": download_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "expires_in": 900,
    }
