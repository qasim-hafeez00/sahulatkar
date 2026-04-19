import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator

import fakeredis.aioredis
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sk_shared.models import auth, contracts, order, payment, product, kyc  # register models
from sk_shared.models.base import Base
from sk_shared.redis_client import RedisClient
from sk_shared.security import create_access_token, get_password_hash

from src.config import settings
from src.core.dependencies import get_db as service_get_db
from src.core.dependencies import get_redis
from src.main import app


# SQLite only auto-generates PK values for INTEGER PRIMARY KEY.
# Shared models use BigInteger PKs, so compile them as INTEGER in tests.
@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


def generate_test_keys() -> tuple[str, str]:
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


TEST_DB_PATH = "./payment_orchestrator_test.db"
test_engine = create_async_engine(
    f"sqlite+aiosqlite:///{TEST_DB_PATH}",
    echo=False,
)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def setup_test_keys():
    priv, pub = generate_test_keys()
    settings.JWT_PRIVATE_KEY = priv
    settings.JWT_PUBLIC_KEY = pub


@pytest.fixture
def redis_mock() -> RedisClient:
    from fakeredis.aioredis import FakeRedis

    return RedisClient(FakeRedis())


@pytest.fixture
def override_dependencies(redis_mock: RedisClient):
    app.dependency_overrides[service_get_db] = override_get_db
    app.state.redis = redis_mock

    def override_get_redis(request: Request):
        return redis_mock

    app.dependency_overrides[get_redis] = override_get_redis
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def db_setup():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(override_dependencies) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_user():
    from sk_shared.models.auth import User

    async with TestingSessionLocal() as session:
        user = User(uuid=uuid.uuid4(), phone="+923001234567", status="pending_kyc")
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token({"user_id": user.id}, settings.JWT_PRIVATE_KEY, timedelta(seconds=900))
    return user, token


@pytest.fixture
def seed_signed_order():
    async def _seed_signed_order(user_id: int, status: str = "contracts_signed"):
        from sk_shared.models.contracts import MurabahaContract
        from sk_shared.models.order import Order
        from sk_shared.models.product import Merchant, Product

        async with TestingSessionLocal() as session:
            merchant = Merchant(name="Test Merchant", normalized_name="test-merchant", domain="example.com")
            session.add(merchant)
            await session.flush()

            product = Product(
                merchant_id=merchant.id,
                name="Test Product",
                url="https://example.com/product/1",
                currency="PKR",
                cost_price=5000,
                sale_price=5200,
                in_stock=True,
            )
            session.add(product)
            await session.flush()

            order_row = Order(
                user_id=user_id,
                product_id=product.id,
                status=status,
                total_amount=5200,
                down_payment_amount=1300,
            )
            session.add(order_row)
            await session.flush()

            contract = MurabahaContract(
                order_id=order_row.id,
                user_id=user_id,
                contract_number=f"MUR-{order_row.id}",
                cost_price=5000,
                profit_amount=200,
                profit_rate_pct=4,
                total_sale_price=5200,
                installment_count=1,
                installment_schedule={"installments": 1},
                contract_pdf_path="/tmp/contract.pdf",
                contract_hash="abc123",
                otp_reference="otp-123",
                signed_at=None,
            )
            if status == "contracts_signed":
                contract.signed_at = datetime.utcnow()
            session.add(contract)
            await session.commit()
            await session.refresh(order_row)
            return order_row, contract

    return _seed_signed_order