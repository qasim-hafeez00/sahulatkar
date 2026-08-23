import pytest
import uuid
import hashlib
import sys
from pathlib import Path
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



def _bootstrap_project_root() -> None:
    current_file = Path(__file__).resolve()
    for candidate in current_file.parents:
        if (candidate / "src" / "services" / "kyc.py").exists() and (candidate / "src" / "main.py").exists():
            project_root = candidate
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            return


_bootstrap_project_root()

from sk_shared.redis_client import RedisClient
from sk_shared.security import create_access_token
from sk_shared.models.base import Base
try:
    from sk_shared.models import delivery   # Shipment, TrackingEvent
except ImportError:
    delivery = None

try:
    from src.main import app
except ModuleNotFoundError:
    app = None

try:
    from src.config import settings
except ModuleNotFoundError:
    class _FallbackSettings:
        pass

    settings = _FallbackSettings()


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
    # 1024-bit is sufficient for ephemeral test tokens and much faster to generate.
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
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

# ── In-memory database (Cache=shared is critical for concurrency in SQLite) ────────
test_engine = create_async_engine("sqlite+aiosqlite:///:memory:?cache=shared", echo=False)
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


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    orig_env = settings.ENVIRONMENT
    orig_mfa = settings.REQUIRE_ADMIN_MFA
    orig_jazzcash_secret = settings.JAZZCASH_WEBHOOK_SECRET
    orig_safepay_secret = settings.SAFEPAY_WEBHOOK_SECRET
    settings.ENVIRONMENT = "test"
    settings.REQUIRE_ADMIN_MFA = False
    settings.JAZZCASH_WEBHOOK_SECRET = "test-jazzcash-webhook-secret"
    settings.SAFEPAY_WEBHOOK_SECRET = "test-safepay-webhook-secret"
    yield
    settings.ENVIRONMENT = orig_env
    settings.REQUIRE_ADMIN_MFA = orig_mfa
    settings.JAZZCASH_WEBHOOK_SECRET = orig_jazzcash_secret
    settings.SAFEPAY_WEBHOOK_SECRET = orig_safepay_secret


@pytest.fixture
def redis_mock() -> RedisClient:
    from fakeredis.aioredis import FakeRedis
    return RedisClient(FakeRedis())


try:
    from src.core.dependencies import get_db as gateway_get_db
except ModuleNotFoundError:
    gateway_get_db = None

@pytest.fixture
def override_dependencies(db_session: AsyncSession, redis_mock: RedisClient):
    if app is None or gateway_get_db is None:
        yield None
        return

    async def shared_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestingSessionLocal() as session:
            yield session

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
    # In-memory DB is clean on each startup, but shared cache persists across connections.
    # We clear it explicitly at the start of each test.
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # No explicit drop needed at end for in-memory, but good for cleanliness.
    # async with test_engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)


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
async def test_user(redis_mock: RedisClient):
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
    
    await redis_mock.set(f"sk:auth:session:{acc_hash}", str(user.id), 900)
        
    return user, token


@pytest.fixture
async def test_admin(redis_mock: RedisClient):
    """Seed an admin user and return (admin, access_token)."""
    from sk_shared.models.auth import AdminUser
    async with TestingSessionLocal() as session:
        admin = AdminUser(
            uuid=uuid.uuid4(),
            email="admin@test.com",
            # Password hash is not used by token-based admin fixtures.
            password_hash="fixture-not-used",
            mfa_enabled=False,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)

    token = create_access_token(
        {"admin_id": admin.id, "role": "super_admin", "permissions": ["all_actions"], "token_type": "admin"},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=3600),
    )
    
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await redis_mock.set(
        f"sk:auth:admin_session:{token_hash}",
        f"{admin.id}:super_admin",
        3600,
    )
    # Store admin sessions set as JSON for FakeRedis compatibility
    try:
        if hasattr(redis_mock.redis, "sadd"):
            await redis_mock.redis.sadd(f"sk:auth:admin_sessions:{admin.id}", token_hash)
            await redis_mock.redis.expire(f"sk:auth:admin_sessions:{admin.id}", 3600)
    except Exception:
        # Fallback: store as JSON if sadd not available
        import json
        sessions = await redis_mock.get(f"sk:auth:admin_sessions:{admin.id}")
        if sessions:
            session_set = json.loads(sessions)
        else:
            session_set = []
        session_set.append(token_hash)
        await redis_mock.set(f"sk:auth:admin_sessions:{admin.id}", json.dumps(session_set), 3600)
    
    return admin, token
