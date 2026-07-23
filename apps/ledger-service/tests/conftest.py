import asyncio
import os
import sys
from pathlib import Path

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sk_shared.models.base import Base
from sk_shared.redis_client import RedisClient
from src.main import app
from src.core.database import get_db
from src.core.dependencies import get_redis

TEST_DATABASE_URL = os.getenv("LEDGER_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


# The shared `sk_shared.models` package registers every service's tables onto the
# same Base.metadata (see audit finding on shared-kernel coupling), so importing
# `src.main` here pulls in Postgres-only column types (JSONB/ARRAY/TSVECTOR) from
# other services that SQLite's in-memory test engine can't compile without these.
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


@pytest.fixture(scope="function")
async def engine():
    engine_kwargs = {"echo": False}
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool

    engine = create_async_engine(TEST_DATABASE_URL, **engine_kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(engine):
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def redis_mock() -> RedisClient:
    return RedisClient(fakeredis.aioredis.FakeRedis())

@pytest.fixture
async def client(db_session, redis_mock):
    def override_get_db():
        yield db_session

    def override_get_redis():
        return redis_mock

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.state.redis = redis_mock
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
async def seed_ledger_accounts(db_session):
    from sk_shared.models.ledger import LedgerAccount, CharityOrganization
    from src.accounting.accounts import ACCOUNT_CODES
    
    accounts = [
        LedgerAccount(account_code=code, account_name=name.replace("_", " ").title(), account_type="asset" if code.startswith("1") else "liability" if code.startswith("2") else "equity" if code.startswith("3") else "revenue" if code.startswith("4") else "expense", normal_balance="debit" if code.startswith(("1", "5")) else "credit")
        for name, code in ACCOUNT_CODES.items()
    ]
    db_session.add_all(accounts)
    
    charity = CharityOrganization(
        name="Edhi Foundation",
        bank_iban="PK00EDHI123456789",
        registration_number="CHARITY-EDHI-001",
        approved_by_shariah_board=True,
        is_active=True
    )
    db_session.add(charity)
    
    await db_session.commit()
