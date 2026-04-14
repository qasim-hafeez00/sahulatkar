from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.redis_client import RedisClient

from src.core.dependencies import get_aftership_client, get_db, get_redis, require_operations_manager
from src.schemas.tracking import AdminTrackingIssuesResponse
from src.services.aftership_client import AfterShipClient
from src.services.tracking_service import TrackingService

router = APIRouter(prefix="/admin/tracking", tags=["Admin Tracking"])


@router.get("/issues", response_model=AdminTrackingIssuesResponse, dependencies=[Depends(require_operations_manager)])
async def get_tracking_issues(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    aftership: AfterShipClient = Depends(get_aftership_client),
):
    service = TrackingService(db=db, redis=redis, aftership=aftership)
    issues = await service.get_admin_issues()
    return AdminTrackingIssuesResponse(issues=issues, total=len(issues))
