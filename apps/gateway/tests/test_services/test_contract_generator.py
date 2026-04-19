import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sk_shared.models.kyc import CustomerProfile
from sk_shared.models.order import Order
from src.services.contract_generator import ContractGeneratorService
from src.schemas.contracts import WakalahGenerateRequest
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio

async def test_generate_wakalah_fetches_customer_profile(test_user, redis_mock):
    user, _ = test_user
    async with TestingSessionLocal() as session:
        profile = CustomerProfile(
            user_id=user.id,
            first_name="Test",
            last_name="Profile",
            cnic="42101-1234567-1",
            dob=datetime(1990, 1, 1)
        )
        session.add(profile)
        order = Order(
            user_id=user.id,
            status="pending",
            total_amount=10000,
            down_payment_amount=2500
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        svc = ContractGeneratorService(session)
        req = WakalahGenerateRequest(order_id=order.id)
        
        contract = await svc.generate_wakalah(user.id, req, redis_mock)
        assert contract is not None
        assert contract.principal_name == "Test Profile"

        from src.core.kms import KMSProvider
        assert isinstance(contract.principal_cnic, (bytes, bytearray))
        assert KMSProvider().decrypt(contract.principal_cnic) == "42101-1234567-1"
        assert contract.valid_until is not None
