from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient

from src.core.dependencies import (
    get_aftership_client,
    get_current_user_id,
    get_db,
    get_redis,
    require_internal_key,
)
from src.schemas.tracking import RegisterTrackingRequest, RegisterTrackingResponse, ShipmentStatusResponse
from src.services.aftership_client import AfterShipClient
from src.services.tracking_service import TrackingService

router = APIRouter(prefix="/tracking", tags=["Tracking"])


@router.post("/register", response_model=RegisterTrackingResponse, dependencies=[Depends(require_internal_key)])
async def register_tracking(
    request_payload: RegisterTrackingRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    aftership: AfterShipClient = Depends(get_aftership_client),
):
    service = TrackingService(db=db, redis=redis, aftership=aftership)
    shipment = await service.register_shipment(
        order_id=request_payload.order_id,
        tracking_number=request_payload.tracking_number,
        courier_code=request_payload.courier_code,
    )
    return RegisterTrackingResponse(
        shipment_id=shipment.id,
        aftership_tracking_id=shipment.aftership_tracking_id,
        status=shipment.status,
    )


@router.get("/{order_id}", response_model=ShipmentStatusResponse)
async def get_tracking_status(
    order_id: int,
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    aftership: AfterShipClient = Depends(get_aftership_client),
):
    service = TrackingService(db=db, redis=redis, aftership=aftership)
    return await service.get_shipment_status(order_id=order_id)
