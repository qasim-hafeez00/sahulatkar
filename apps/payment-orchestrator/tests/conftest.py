"""
Stable In-Memory Test Fixtures for Payment Orchestrator.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Models
from sk_shared.models import auth, contracts, order, payment, product, kyc, credit, delivery, hitl, audit
from src.models.payment_workflow import PaymentWorkflow, PaymentEvent
from src.models.outbox import OutboxEvent
from src.models.refund_workflow import RefundWorkflow
from src.models.payment_mandate import PaymentMandate
from sk_shared.models.base import Base
from sk_shared.redis_client import RedisClient
from sk_shared.security import create_access_token

from src.config import settings
from src.core.dependencies import get_db as service_get_db
from src.core.dependencies import get_redis
from src.main import app

@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw):
    return "INTEGER"

# In-memory engine with StaticPool keeps DB alive across connections
engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
TestingSessionLocal = SessionLocal

@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

@pytest.fixture(autouse=True)
def override_db(db_session):
    async def _get_db():
        yield db_session
    app.dependency_overrides[service_get_db] = _get_db
    yield
    app.dependency_overrides.clear()

@pytest.fixture(scope="session", autouse=True)
def setup_keys():
    priv = rsa.generate_private_key(65537, 2048)
    settings.JWT_PRIVATE_KEY = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()).decode()
    settings.JWT_PUBLIC_KEY = priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    settings.INTERNAL_API_TOKEN = "test-internal-token-secret"
    settings.VCN_ENCRYPTION_KEY = "test-vcn-key"
    settings.RECONCILIATION_AUDIT_DIR = "./tmp/recon"

@pytest.fixture
def redis_mock():
    from fakeredis.aioredis import FakeRedis
    return RedisClient(FakeRedis())

@pytest.fixture
async def client(redis_mock):
    app.state.redis = redis_mock
    app.dependency_overrides[get_redis] = lambda: redis_mock
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def test_user(db_session):
    from sk_shared.models.auth import User
    user = User(uuid=uuid.uuid4(), phone="+923001234567", status="kyc_approved")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"user_id": user.id}, settings.JWT_PRIVATE_KEY, timedelta(seconds=900))
    return user, token

@pytest.fixture
async def test_admin(db_session):
    from sk_shared.models.auth import AdminUser
    admin = AdminUser(email="admin@sahulatkar.pk", role="superadmin", status="active")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    token = create_access_token({"admin_id": admin.id, "role": "superadmin"}, settings.JWT_PRIVATE_KEY, timedelta(seconds=900))
    return admin, token

@pytest.fixture
def seed_signed_order(db_session):
    async def _seed(user_id: int, status: str = "contracts_signed") -> tuple:
        from sk_shared.models.contracts import MurabahaContract
        from sk_shared.models.order import Order
        from sk_shared.models.product import Merchant, Product
        merchant = Merchant(name="Test Merchant", normalized_name="test-merchant", domain="example.com")
        db_session.add(merchant)
        await db_session.flush()
        prod = Product(merchant_id=merchant.id, name="Test Product", url="https://example.com/product/1", currency="PKR", cost_price=Decimal("5000"), sale_price=Decimal("5200"), in_stock=True)
        db_session.add(prod)
        await db_session.flush()
        o = Order(user_id=user_id, product_id=prod.id, status=status, total_amount=Decimal("5200"), down_payment_amount=Decimal("1300"))
        db_session.add(o)
        await db_session.flush()
        contract = MurabahaContract(order_id=o.id, user_id=user_id, contract_number=f"MUR-{o.id}", cost_price=Decimal("5000"), profit_amount=Decimal("200"), profit_rate_pct=Decimal("4"), total_sale_price=Decimal("5200"), installment_count=4, installment_schedule={"installments": 4}, contract_pdf_path="/tmp/contract.pdf", contract_hash="abc123", otp_reference="otp-123", signed_at=datetime.now(timezone.utc) if status == "contracts_signed" else None)
        db_session.add(contract)
        await db_session.commit()
        await db_session.refresh(o)
        await db_session.refresh(contract)
        return o, contract
    return _seed

@pytest.fixture
def seed_order_with_loan(db_session):
    async def _seed(user_id: int) -> tuple:
        from sk_shared.models.contracts import MurabahaContract
        from sk_shared.models.order import Order
        from sk_shared.models.payment import Installment, Loan
        from sk_shared.models.product import Merchant, Product
        merchant = Merchant(name="Seeded Merchant", normalized_name="seeded-merchant", domain="seeded.com")
        db_session.add(merchant)
        await db_session.flush()
        prod = Product(merchant_id=merchant.id, name="Seeded Product", url="https://seeded.com/product/1", currency="PKR", cost_price=Decimal("5000"), sale_price=Decimal("5200"), in_stock=True)
        db_session.add(prod)
        await db_session.flush()
        o = Order(user_id=user_id, product_id=prod.id, status="down_payment_received", total_amount=Decimal("5200"), down_payment_amount=Decimal("1300"))
        db_session.add(o)
        await db_session.flush()
        contract = MurabahaContract(order_id=o.id, user_id=user_id, contract_number=f"MUR-LOAN-{o.id}", cost_price=Decimal("5000"), profit_amount=Decimal("200"), profit_rate_pct=Decimal("4"), total_sale_price=Decimal("5200"), installment_count=4, installment_schedule={"installments": 4}, contract_pdf_path="/tmp/contract.pdf", contract_hash="abc456", otp_reference="otp-456", signed_at=datetime.now(timezone.utc))
        db_session.add(contract)
        await db_session.flush()
        loan = Loan(order_id=o.id, user_id=user_id, murabaha_contract_id=contract.id, loan_number=f"SAK-LOAN-{o.id:010d}", principal_amount=Decimal("5000"), profit_amount=Decimal("200"), total_repayable=Decimal("5200"), down_payment_amount=Decimal("1300"), balance_financed=Decimal("3900"), profit_rate_pct=Decimal("4"), plan_type="murabaha_installment", installment_count=4, installment_amount=Decimal("975"), status="active", total_paid=Decimal("1300"), total_outstanding=Decimal("3900"), late_fee_total=Decimal("0"))
        db_session.add(loan)
        await db_session.flush()
        for i in range(1, 5):
            inst = Installment(loan_id=loan.id, user_id=user_id, installment_number=i, is_down_payment=False, principal_portion=Decimal("925"), profit_portion=Decimal("50"), total_amount=Decimal("975"), due_date=(datetime.now(timezone.utc) + timedelta(days=14 * i)).date(), status="pending", paid_amount=Decimal("0"), days_overdue=0, late_fee_amount=Decimal("0"), late_fee_waived=False, retry_count=0)
            db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(o)
        await db_session.refresh(loan)
        return o, loan
    return _seed