import uuid
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sk_shared.models.auth import User
from sk_shared.models.base import Base
from sk_shared.models.kyc import KycStatus, UserKycVerification
from src.main import app
from src.core.dependencies import get_db, get_redis

import fakeredis.aioredis
from sk_shared.redis_client import RedisClient
from sk_shared.models.credit import CreditApplication, RiskAssessment, CreditLimitHistory, BlacklistedEntity, FraudRule, VelocityCheck

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def redis_mock() -> RedisClient:
    return RedisClient(fakeredis.aioredis.FakeRedis())


@pytest_asyncio.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session, redis_mock):
    async def override_get_db():
        yield db_session

    def override_get_redis():
        return redis_mock

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    app.state.redis = redis_mock

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def approved_user(db_session):
    user = User(uuid=uuid.uuid4(), phone="+923001234567", status="active")
    db_session.add(user)
    await db_session.flush()

    kyc = UserKycVerification(
        user_id=user.id,
        status=KycStatus.APPROVED,
        nadra_verification_data={"confidence": 0.92},
        shufti_verification_data={"face_match_score": 0.90, "liveness_score": 0.88},
    )
    db_session.add(kyc)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def pending_kyc_user(db_session):
    user = User(uuid=uuid.uuid4(), phone="+923009999999", status="active")
    db_session.add(user)
    await db_session.flush()

    kyc = UserKycVerification(
        user_id=user.id,
        status=KycStatus.PENDING,
        nadra_verification_data={"confidence": 0.3},
        shufti_verification_data={"face_match_score": 0.2, "liveness_score": 0.2},
    )
    db_session.add(kyc)
    await db_session.commit()
    await db_session.refresh(user)
    return user
