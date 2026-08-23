import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.notification_service import NotificationService
from sk_shared.models.notification import Notification

@pytest.fixture
def mock_deps():
    return AsyncMock(), AsyncMock()

@pytest.mark.asyncio
async def test_create_notification_idempotent(mock_deps):
    mock_db, mock_redis = mock_deps
    mock_db.scalar.return_value = Notification(id=1, idempotency_key="key1")
    
    svc = NotificationService(db=mock_db, redis=mock_redis)
    result = await svc.create_notification(
        user_id=1, event_type="kyc.approved", template_vars={}, idempotency_key="key1"
    )
    
    assert result.id == 1
    mock_db.add.assert_not_called()

@pytest.mark.asyncio
async def test_send_otp_success(mock_deps):
    mock_db, mock_redis = mock_deps
    mock_redis.incr.return_value = 1
    mock_db.scalar.return_value = None # No existing user check or similar
    
    svc = NotificationService(db=mock_db, redis=mock_redis)
    with patch.object(svc, 'dispatch_notification', new_callable=AsyncMock) as mock_dispatch:
        result = await svc.send_otp(phone="+923001234567", otp_code="123456", purpose="test")
        
        assert result["status"] == "sent"
        # 1 for Notification, 1 for Dispatch
        assert mock_db.add.call_count >= 2
        mock_dispatch.assert_called_once()

@pytest.mark.asyncio
async def test_send_otp_rate_limited(mock_deps):
    mock_db, mock_redis = mock_deps
    mock_redis.incr.return_value = 100 # Exceeds limit
    
    svc = NotificationService(db=mock_db, redis=mock_redis)
    result = await svc.send_otp(phone="+923001234567", otp_code="123456", purpose="test")
    
    assert result["status"] == "rate_limited"
    mock_db.add.assert_not_called()

@pytest.mark.asyncio
async def test_create_bulk_notifications(mock_deps):
    mock_db, mock_redis = mock_deps
    mock_db.scalar.return_value = None # Not duplicate
    
    svc = NotificationService(db=mock_db, redis=mock_redis)
    notifications = [
        {"user_id": 1, "template_vars": {}, "idempotency_key": "bulk1"},
        {"user_id": 2, "template_vars": {}, "idempotency_key": "bulk2"},
    ]
    
    with patch.object(svc, 'create_notification', new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            MagicMock(id=101),
            MagicMock(id=102)
        ]
        stats = await svc.create_bulk_notifications(event_type="test.event", notifications=notifications)
        
        assert stats["accepted"] == 2
        assert len(stats["queued_notification_ids"]) == 2
        assert mock_create.call_count == 2

@pytest.mark.asyncio
async def test_shariah_compliance_filtering_bypass(mock_deps):
    mock_db, mock_redis = mock_deps
    # Mock db.scalar to return None (no existing notification)
    mock_db.scalar.return_value = None
    
    svc = NotificationService(db=mock_db, redis=mock_redis)
    svc.preference_service.filter_channels = AsyncMock(return_value=[])
    
    # Event is compliance
    event_type = "billing.late_fee_applied"
    
    # Mocking flush and commit to avoid actual DB ops
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    
    with patch.object(svc, '_enqueue', new_callable=AsyncMock):
        result = await svc.create_notification(
            user_id=1, 
            event_type=event_type, 
            template_vars={"fee_amount": "500"}, 
            idempotency_key="comp-test"
        )
        
        # Compliance should bypass filtering in NotificationService logic
        svc.preference_service.filter_channels.assert_not_called()
        assert len(result.channels_requested) > 0
