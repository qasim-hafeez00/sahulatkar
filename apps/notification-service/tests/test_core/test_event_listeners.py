import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from src.core.event_listeners import listen_to_redis_events

@pytest.mark.asyncio
async def test_listen_to_redis_events():
    app = FastAPI()
    mock_redis = MagicMock()
    mock_pubsub = AsyncMock()
    
    # Mock Redis client structure
    mock_redis._client = MagicMock()
    mock_redis._client.pubsub.return_value = mock_pubsub
    
    app.state.redis = mock_redis
    
    # Mock the generator of listen()
    async def mock_listen():
        yield {
            "type": "message",
            "channel": b"sahulatkar:events:kyc.approved",
            "data": json.dumps({"user_id": 1, "payload": {"user_id": 1, "credit_limit": "50000"}})
        }
        # Cancel after one message to exit loop
        raise asyncio.CancelledError()
        
    mock_pubsub.listen = mock_listen
    
    mock_db_factory = MagicMock()
    mock_db = AsyncMock()
    mock_db_factory.return_value.__aenter__.return_value = mock_db
    app.state.db_factory = mock_db_factory
    
    with patch("src.core.event_listeners.NotificationService") as MockSvc:
        svc_instance = MockSvc.return_value
        svc_instance.create_notification = AsyncMock()
        
        await listen_to_redis_events(app)
        
        svc_instance.create_notification.assert_called_once()
        args, kwargs = svc_instance.create_notification.call_args
        assert kwargs["user_id"] == 1
        assert kwargs["event_type"] == "kyc.approved"
        assert kwargs["template_vars"]["credit_limit"] == "50000"
