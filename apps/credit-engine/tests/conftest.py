import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from sk_shared.models.auth import AdminUser, User
from sk_shared.models.base import Base
from sk_shared.models.kyc import KycStatus, UserKycVerification
from sk_shared.security import create_access_token
from src.config import settings
from src.main import app
from src.core.dependencies import get_db, get_redis

import fakeredis.aioredis
from sk_shared.redis_client import RedisClient
from sk_shared.models.credit import CreditApplication, RiskAssessment, CreditLimitHistory, BlacklistedEntity, FraudRule, VelocityCheck


# The shared `sk_shared.models` package registers every service's tables onto the
# same Base.metadata (see audit finding on shared-kernel coupling), so importing
# any model here pulls in Postgres-only column types (JSONB/ARRAY/TSVECTOR) that
# SQLite's in-memory test engine can't compile without these shims.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type, _compiler, **_kw):
    return "JSON"


try:
    from sqlalchemy.dialects.postgresql import TSVECTOR

    @compiles(TSVECTOR, "sqlite")
    def _compile_tsvector_sqlite(_type, _compiler, **_kw):
        return "TEXT"
except ImportError:
    pass


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


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


@pytest.fixture(scope="session", autouse=True)
def setup_keys():
    priv = rsa.generate_private_key(65537, 2048)
    settings.JWT_PRIVATE_KEY = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()
    ).decode()
    settings.JWT_PUBLIC_KEY = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def _bearer_headers(claims: dict) -> dict:
    token = create_access_token(claims, settings.JWT_PRIVATE_KEY, timedelta(seconds=900))
    return {"Authorization": f"Bearer {token}"}


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
def auth_headers():
    """Factory returning valid Authorization headers for a given customer User."""
    def _make(user: User) -> dict:
        return _bearer_headers({"user_id": user.id})
    return _make


@pytest_asyncio.fixture
async def risk_admin(db_session) -> AdminUser:
    admin = AdminUser(email="risk-admin@sahulatkar.pk", password_hash="unused")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest_asyncio.fixture
def admin_headers():
    """Factory returning valid Authorization headers for a given AdminUser."""
    def _make(admin: AdminUser) -> dict:
        return _bearer_headers({"admin_id": admin.id, "role": "risk_admin"})
    return _make


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
