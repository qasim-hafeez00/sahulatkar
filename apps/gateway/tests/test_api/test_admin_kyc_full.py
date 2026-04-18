import pytest
from sqlalchemy import select
from sk_shared.models.kyc import UserKycVerification, KycVerificationQueue, KycStatus
from sk_shared.models.auth import User
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio

async def test_kyc_approval_activates_user(client, test_admin):
    admin, token = test_admin
    headers = {"Authorization": f"Bearer {token}"}
    
    async with TestingSessionLocal() as session:
        user = User(phone="+923000000002", status="pending_kyc")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        kyc = UserKycVerification(user_id=user.id, status=KycStatus.SUBMITTED)
        session.add(kyc)
        await session.commit()
        await session.refresh(kyc)
        
        queue = KycVerificationQueue(kyc_verification_id=kyc.id)
        session.add(queue)
        await session.commit()
        await session.refresh(queue)
        
        # Admin claims
        queue.assigned_admin_id = admin.id
        await session.commit()
        queue_id = queue.id
        
    resp = await client.post(f"/api/v1/admin/kyc/{queue_id}/decision", json={
        "approved": True
    }, headers=headers)
    
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    
    async with TestingSessionLocal() as session:
        db_user = await session.scalar(select(User).where(User.id == user.id))
        assert db_user.status == "active"
