import pytest
import asyncio
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from httpx import AsyncClient, ASGITransport
from fastapi import Request
from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import fakeredis.aioredis

from sk_shared.database import get_db
from sk_shared.redis_client import RedisClient
from sk_shared.security import create_access_token
from sk_shared.models.base import Base
from sk_shared.models import auth  # registers auth models with Base.metadata
from sk_shared.models import kyc   # registers kyc models with Base.metadata
from sk_shared.models import product  # registers product models with Base.metadata
from sk_shared.models import order  # registers order models with Base.metadata
from sk_shared.models import contracts  # registers contract models with Base.metadata
from sk_shared.models import hitl       # HitlQueue
from sk_shared.models import payment    # Loan, Installment, PaymentTransaction, VirtualCard
from sk_shared.models import delivery   # Shipment, TrackingEvent
from sk_shared.models import audit      # AuditTrail
from src.main import app
from src.config import settings


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


# ── RSA key generation ────────────────────────────────────────────────────────

def generate_test_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem.decode("utf-8"), public_pem.decode("utf-8")


# ── In-memory database ────────────────────────────────────────────────────────

test_engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


# ── Session-scoped fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_test_keys():
    priv, pub = generate_test_keys()
    settings.JWT_PRIVATE_KEY = priv
    settings.JWT_PUBLIC_KEY = pub


@pytest.fixture
def redis_mock() -> RedisClient:
    from fakeredis.aioredis import FakeRedis
    return RedisClient(FakeRedis())


from src.core.dependencies import get_db as gateway_get_db

@pytest.fixture
def override_dependencies(db_session: AsyncSession, redis_mock: RedisClient):
    async def shared_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[gateway_get_db] = shared_get_db
    app.state.redis = redis_mock
    
    def override_get_redis(request: Request):
        return redis_mock
        
    from src.core.dependencies import get_redis
    app.dependency_overrides[get_redis] = override_get_redis
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def db_setup():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(override_dependencies) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── User / Admin helpers ──────────────────────────────────────────────────────

@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def test_user():
    """Seed a customer user and return (user, access_token)."""
    from sk_shared.models.auth import User
    async with TestingSessionLocal() as session:
        user = User(uuid=uuid.uuid4(), phone="+923001234567", status="pending_kyc")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token(
        {"user_id": user.id},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=900),
    )
    
    # NEW: Create session in DB and Redis
    from sk_shared.models.auth import UserSession
    acc_hash = hashlib.sha256(token.encode()).hexdigest()
    async with TestingSessionLocal() as session:
        user_session = UserSession(
            user_id=user.id,
            access_token_hash=acc_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=900)
        )
        session.add(user_session)
        await session.commit()
    
    # redis_mock is a local fixture, we need to access it. 
    # But fixtures are requested by name in the test function.
    # In conftest, we can use request.getfixturevalue if needed, 
    # but the easiest way is to push to app.state.redis directly if available.
    if hasattr(app.state, "redis"):
        await app.state.redis.set(f"sk:auth:session:{acc_hash}", str(user.id), 900)
        
    return user, token


@pytest.fixture
async def test_admin():
    """Seed an admin user and return (admin, access_token)."""
    from sk_shared.models.auth import AdminUser
    from sk_shared.security import get_password_hash
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            uuid=uuid.uuid4(),
            email="admin@test.com",
            password_hash=get_password_hash("S3cr3t!"),
            mfa_enabled=False,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {"admin_id": admin.id, "role": "super_admin", "permissions": ["all_actions"]},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=3600),
    )
    
    # NEW: Redis session for admin (if we added admin session checking to dependencies)
    # The current get_current_admin in dependencies.py doesn't yet check Redis session 
    # (only user login does in this iteration), but we set the token correctly for RBAC.
    
    return admin, token
