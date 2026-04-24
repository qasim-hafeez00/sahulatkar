"""
Test fixtures for payment orchestrator.

All tests use:
  - In-memory SQLite (aiosqlite) for zero-dependency fast execution
  - fakeredis for Redis operations
  - RSA key pair generated per test session for JWT signing/verification
  - Fixture factories for signed orders, contracts, loans, and installments
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from sk_shared.models import auth, contracts, order, payment, product, kyc  # register all models
from sk_shared.models.base import Base
from sk_shared.redis_client import RedisClient
from sk_shared.security import create_access_token

from src.config import settings
from src.core.dependencies import get_db as service_get_db
from src.core.dependencies import get_redis
from src.main import app


# SQLite does not support BigInteger — compile as INTEGER for test compatibility
@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"


# ── Key Generation ────────────────────────────────────────────────────────────

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
    return private_pem.decode(), public_pem.decode()


# ── Database ──────────────────────────────────────────────────────────────────

TEST_DB_PATH = "./payment_orchestrator_test.db"
test_engine = create_async_engine(f"sqlite+aiosqlite:///{TEST_DB_PATH}", echo=False)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine, expire_on_commit=False
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


# ── Session-scoped Setup ──────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_test_keys():
    priv, pub = generate_test_keys()
    settings.JWT_PRIVATE_KEY = priv
    settings.JWT_PUBLIC_KEY = pub
    settings.INTERNAL_API_TOKEN = "test-internal-token-secret"
    settings.VCN_ENCRYPTION_KEY = "test-vcn-key-for-unit-tests"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
async def db_setup():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Redis Mock ────────────────────────────────────────────────────────────────

@pytest.fixture
def redis_mock() -> RedisClient:
    from fakeredis.aioredis import FakeRedis
    return RedisClient(FakeRedis())


@pytest.fixture
def override_dependencies(redis_mock: RedisClient):
    app.dependency_overrides[service_get_db] = override_get_db
    app.state.redis = redis_mock

    def _override_redis(request: Request):
        return redis_mock

    app.dependency_overrides[get_redis] = _override_redis
    yield app
    app.dependency_overrides.clear()


# ── HTTP Client ───────────────────────────────────────────────────────────────

@pytest.fixture
async def client(override_dependencies) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── User / Admin Factories ───────────────────────────────────────────────────

@pytest.fixture
async def test_user():
    from sk_shared.models.auth import User
    async with TestingSessionLocal() as session:
        user = User(uuid=uuid.uuid4(), phone="+923001234567", status="kyc_approved")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token(
        {"user_id": user.id}, settings.JWT_PRIVATE_KEY, timedelta(seconds=900)
    )
    return user, token


@pytest.fixture
async def test_admin():
    from sk_shared.models.auth import AdminUser
    async with TestingSessionLocal() as session:
        admin = AdminUser(email="admin@sahulatkar.pk", role="superadmin", status="active")
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
    token = create_access_token(
        {"admin_id": admin.id, "role": "superadmin"},
        settings.JWT_PRIVATE_KEY,
        timedelta(seconds=900),
    )
    return admin, token


# ── Order / Contract / Loan Factories ────────────────────────────────────────

@pytest.fixture
def seed_signed_order():
    async def _seed(user_id: int, status: str = "contracts_signed") -> tuple:
        from sk_shared.models.contracts import MurabahaContract
        from sk_shared.models.order import Order
        from sk_shared.models.product import Merchant, Product

        async with TestingSessionLocal() as session:
            merchant = Merchant(name="Test Merchant", normalized_name="test-merchant", domain="example.com")
            session.add(merchant)
            await session.flush()

            prod = Product(
                merchant_id=merchant.id,
                name="Test Product",
                url="https://example.com/product/1",
                currency="PKR",
                cost_price=Decimal("5000"),
                sale_price=Decimal("5200"),
                in_stock=True,
            )
            session.add(prod)
            await session.flush()

            o = Order(
                user_id=user_id,
                product_id=prod.id,
                status=status,
                total_amount=Decimal("5200"),
                down_payment_amount=Decimal("1300"),
            )
            session.add(o)
            await session.flush()

            contract = MurabahaContract(
                order_id=o.id,
                user_id=user_id,
                contract_number=f"MUR-{o.id}",
                cost_price=Decimal("5000"),
                profit_amount=Decimal("200"),
                profit_rate_pct=Decimal("4"),
                total_sale_price=Decimal("5200"),
                installment_count=4,
                installment_schedule={"installments": 4},
                contract_pdf_path="/tmp/contract.pdf",
                contract_hash="abc123",
                otp_reference="otp-123",
                signed_at=datetime.now(timezone.utc) if status == "contracts_signed" else None,
            )
            session.add(contract)
            await session.commit()
            await session.refresh(o)
            await session.refresh(contract)
            return o, contract

    return _seed


@pytest.fixture
def seed_order_with_loan():
    """Seed an order that already has a Loan and Installments (post down payment)."""
    async def _seed(user_id: int) -> tuple:
        from sk_shared.models.contracts import MurabahaContract
        from sk_shared.models.order import Order
        from sk_shared.models.payment import Installment, Loan
        from sk_shared.models.product import Merchant, Product

        async with TestingSessionLocal() as session:
            merchant = Merchant(name="Seeded Merchant", normalized_name="seeded-merchant", domain="seeded.com")
            session.add(merchant)
            await session.flush()

            prod = Product(
                merchant_id=merchant.id,
                name="Seeded Product",
                url="https://seeded.com/product/1",
                currency="PKR",
                cost_price=Decimal("5000"),
                sale_price=Decimal("5200"),
                in_stock=True,
            )
            session.add(prod)
            await session.flush()

            o = Order(
                user_id=user_id,
                product_id=prod.id,
                status="down_payment_received",
                total_amount=Decimal("5200"),
                down_payment_amount=Decimal("1300"),
            )
            session.add(o)
            await session.flush()

            contract = MurabahaContract(
                order_id=o.id,
                user_id=user_id,
                contract_number=f"MUR-LOAN-{o.id}",
                cost_price=Decimal("5000"),
                profit_amount=Decimal("200"),
                profit_rate_pct=Decimal("4"),
                total_sale_price=Decimal("5200"),
                installment_count=4,
                installment_schedule={"installments": 4},
                contract_pdf_path="/tmp/contract.pdf",
                contract_hash="abc456",
                otp_reference="otp-456",
                signed_at=datetime.now(timezone.utc),
            )
            session.add(contract)
            await session.flush()

            loan = Loan(
                order_id=o.id,
                user_id=user_id,
                murabaha_contract_id=contract.id,
                loan_number=f"SAK-LOAN-{o.id:010d}",
                principal_amount=Decimal("5000"),
                profit_amount=Decimal("200"),
                total_repayable=Decimal("5200"),
                down_payment_amount=Decimal("1300"),
                balance_financed=Decimal("3900"),
                profit_rate_pct=Decimal("4"),
                plan_type="murabaha_installment",
                installment_count=4,
                installment_amount=Decimal("975"),
                status="active",
                total_paid=Decimal("1300"),
                total_outstanding=Decimal("3900"),
                late_fee_total=Decimal("0"),
            )
            session.add(loan)
            await session.flush()

            # Seed 4 future installments
            for i in range(1, 5):
                inst = Installment(
                    loan_id=loan.id,
                    user_id=user_id,
                    installment_number=i,
                    is_down_payment=False,
                    principal_portion=Decimal("925"),
                    profit_portion=Decimal("50"),
                    total_amount=Decimal("975"),
                    due_date=(datetime.now(timezone.utc) + timedelta(days=14 * i)).date(),
                    status="pending",
                    paid_amount=Decimal("0"),
                    days_overdue=0,
                    late_fee_amount=Decimal("0"),
                    late_fee_waived=False,
                    retry_count=0,
                )
                session.add(inst)

            await session.commit()
            await session.refresh(o)
            await session.refresh(loan)
            return o, loan

    return _seed