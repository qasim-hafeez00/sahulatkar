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

    # listen_to_redis_events() calls `app.state.redis.redis.pubsub()` (RedisClient
    # wraps the real client as `.redis`, not `._client` — see
    # sk_shared/redis_client.py). Mocking the wrong attribute name left
    # `.redis.pubsub()` as an unconfigured MagicMock whose `.subscribe(...)`
    # isn't awaitable, so every real run of this test hit the `except Exception`
    # branch and looped forever on `await asyncio.sleep(5)` — the mocked
    # CancelledError from mock_listen() below was never reached because
    # mock_pubsub itself was never returned to the code under test.
    mock_redis.redis = MagicMock()
    mock_redis.redis.pubsub.return_value = mock_pubsub

    app.state.redis = mock_redis
    
    # Mock the generator of listen()
    async def mock_listen():
        yield {
            "type": "message",
            "channel": b"sk:events:kyc.approved",
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
