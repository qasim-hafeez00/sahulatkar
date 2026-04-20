import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from decimal import Decimal

import fakeredis.aioredis
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sk_shared.models import auth, contracts, credit, kyc, order, payment, product  # noqa: F401
from sk_shared.models.base import Base
from sk_shared.models.checkout import PurchaseExecution
from sk_shared.models.product import Product, ScrapingJob
from sk_shared.redis_client import RedisClient

from src.core.dependencies import get_db as service_get_db
from src.core.dependencies import get_redis
from src.main import app


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
def override_dependencies(redis_mock: RedisClient):
    app.dependency_overrides[service_get_db] = override_get_db
    app.state.redis = redis_mock

    def override_get_redis(request: Request) -> RedisClient:
        return redis_mock

    app.dependency_overrides[get_redis] = override_get_redis
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
def user_header() -> dict[str, str]:
    return {
        "x-user-id": "101",
        "X-Internal-Service-Token": "dev-secret-token"
    }


@pytest.fixture
def service_header() -> dict[str, str]:
    return {"X-Internal-Service-Token": "dev-secret-token"}


@pytest.fixture
def make_product():
    async def _make(db_session: AsyncSession, **overrides) -> Product:
        payload = {
            "name": "Fixture Product",
            "url": "https://example.com/p/fixture",
            "canonical_url": "https://example.com/p/fixture",
            "platform": "CUSTOM",
            "currency": "PKR",
            "cost_price": Decimal("5000.00"),
            "sale_price": Decimal("5000.00"),
            "stock_status": "in_stock",
            "in_stock": True,
            "extraction_method": "json_ld",
            "extraction_confidence": Decimal("0.850"),
        }
        payload.update(overrides)
        row = Product(**payload)
        db_session.add(row)
        await db_session.flush()
        return row

    return _make


@pytest.fixture
def make_execution():
    async def _make(db_session: AsyncSession, **overrides) -> PurchaseExecution:
        payload = {
            "order_id": 1,
            "vcn_id": 1,
            "status": "queued",
            "step_reached": "queued",
            "queued_at": datetime.now(timezone.utc),
        }
        payload.update(overrides)
        row = PurchaseExecution(**payload)
        db_session.add(row)
        await db_session.flush()
        return row

    return _make


@pytest.fixture
def make_scraping_job():
    async def _make(db_session: AsyncSession, **overrides) -> ScrapingJob:
        payload = {
            "input_url": "https://example.com/p/fixture",
            "canonical_url": "https://example.com/p/fixture",
            "platform_detected": "CUSTOM",
            "status": "queued",
            "queued_at": datetime.now(timezone.utc),
        }
        payload.update(overrides)
        row = ScrapingJob(**payload)
        db_session.add(row)
        await db_session.flush()
        return row

    return _make


def make_job_payload(job_id: uuid.UUID, canonical_url: str, platform: str = "CUSTOM") -> dict:
    return {
        "job_id": str(job_id),
        "input_url": canonical_url,
        "canonical_url": canonical_url,
        "platform": platform,
        "user_id": 101,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
