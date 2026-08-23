import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from sk_shared.models import auth, contracts, credit, delivery, hitl, kyc, order, payment, product  # noqa: F401
from sk_shared.models.auth import User
from sk_shared.models.delivery import Courier
from sk_shared.models.order import Order
from sk_shared.models.base import Base
from sk_shared.redis_client import RedisClient

from src.config import settings
from src.core.dependencies import get_aftership_client, get_db as service_get_db, get_redis
from src.main import app
from src.services.aftership_client import AfterShipClient


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(TSVECTOR, "sqlite")
def _compile_tsvector_sqlite(_type, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
def redis_mock() -> RedisClient:
    return RedisClient(fakeredis.aioredis.FakeRedis())


@pytest.fixture
def aftership_mock() -> AsyncMock:
    mock = AsyncMock(spec=AfterShipClient)
    mock.create_tracking = AsyncMock(
        return_value={
            "id": "AT-123",
            "tracking_number": "TCS-12345",
            "tag": "Pending",
        }
    )
    return mock


@pytest.fixture
def override_dependencies(redis_mock: RedisClient, aftership_mock: AsyncMock):
    app.dependency_overrides[service_get_db] = override_get_db
    app.state.redis = redis_mock

    def override_get_redis(request: Request) -> RedisClient:
        return redis_mock

    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[get_aftership_client] = lambda _request=None: aftership_mock
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def db_setup() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(override_dependencies) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
def internal_header() -> dict[str, str]:
    return {"x-internal-key": settings.INTERNAL_API_KEY}


@pytest.fixture
def user_header() -> dict[str, str]:
    return {"x-user-id": "42"}


@pytest.fixture
def admin_header() -> dict[str, str]:
    """A validly-signed admin assertion for `operations_manager` with full permissions.

    Mirrors what the Gateway mints via InternalServiceClient.notification_admin_headers
    after authenticating the admin itself — tests can no longer just set the raw
    X-Admin-Role/X-Admin-Permissions headers, since those are no longer trusted.
    """
    from sk_shared.security import create_signed_assertion

    assertion = create_signed_assertion(
        {
            "admin_id": 1,
            "role": "operations_manager",
            "permissions": ["admin:notifications:read", "admin:notifications:write"],
        },
        secret=settings.INTERNAL_API_KEY,
    )
    return {"x-admin-assertion": assertion}


async def seed_couriers(session: AsyncSession) -> None:
    couriers = [
        Courier(name="TCS", code="TCS", aftership_slug="tcs-pak", avg_delivery_days=3),
        Courier(name="Leopards", code="LEO", aftership_slug="leopards-courier", avg_delivery_days=3),
    ]
    session.add_all(couriers)
    await session.commit()


async def seed_user_order(session: AsyncSession, order_status: str = "purchase_confirmed", user_id: int = 42) -> Order:
    user = User(phone=f"+92300{user_id:07d}", status="active")
    session.add(user)
    await session.flush()

    order_row = Order(
        user_id=user.id,
        product_id=None,
        status=order_status,
        total_amount=5200,
        down_payment_amount=1300,
        product_description="Test item",
    )
    session.add(order_row)
    await session.commit()
    await session.refresh(order_row)
    return order_row


def build_webhook_payload(order_id: int, tracking_number: str, tag: str, aftership_id: str = "AT-123") -> dict:
    checkpoint_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "msg": {
            "tracking": {
                "id": aftership_id,
                "order_id": str(order_id),
                "tracking_number": tracking_number,
                "tag": tag,
                "slug": "tcs-pak",
                "checkpoints": [
                    {
                        "tag": tag,
                        "message": f"Status {tag}",
                        "city": "Karachi",
                        "checkpoint_time": checkpoint_time,
                    }
                ],
            }
        }
    }


def make_aftership_signature(payload: dict) -> str:
    body = json.dumps(payload).encode("utf-8")
    return hmac.new(settings.AFTERSHIP_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _set_webhook_secret():
    settings.AFTERSHIP_WEBHOOK_SECRET = "test-aftership-secret"
