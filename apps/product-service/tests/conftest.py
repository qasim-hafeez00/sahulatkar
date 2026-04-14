import uuid
from datetime import datetime
from typing import AsyncGenerator

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
    return {"x-user-id": "101"}


def make_job_payload(job_id: uuid.UUID, canonical_url: str, platform: str = "CUSTOM") -> dict:
    return {
        "job_id": str(job_id),
        "input_url": canonical_url,
        "canonical_url": canonical_url,
        "platform": platform,
        "user_id": 101,
        "queued_at": datetime.utcnow().isoformat(),
    }
