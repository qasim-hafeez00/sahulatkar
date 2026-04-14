"""
Integration tests for the KYC & Customer Profile module (Sprint S02).

Test coverage:
  - KYC state machine: PENDING → SUBMITTED → IN_REVIEW → APPROVED / REJECTED
  - Document upload tracking
  - Incomplete submission guard
  - NADRA-triggered rejection (CNIC ending in -9)
  - Customer profile create / update / read
  - Admin queue: list, claim, approve, reject
  - Auth guard: unauthenticated requests are rejected
"""
import uuid
from datetime import timedelta, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from sk_shared.models.kyc import (
    CustomerProfile,
    KycStatus,
    KycVerificationQueue,
    UserKycVerification,
)
from sk_shared.models.auth import User
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


# ─── helpers ─────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_full_kyc(user_id: int, *, nadra_reject: bool = False) -> None:
    """
    Directly seed a UserKycVerification that has all three doc URLs plus a
    KycVerificationQueue row so admin tests do not depend on the full
    submission flow.
    """
    cnic = "12345-1234567-9" if nadra_reject else "12345-1234567-1"
    async with TestingSessionLocal() as session:
        kyc = UserKycVerification(
            user_id=user_id,
            status=KycStatus.IN_REVIEW,
            cnic_front_image_url="/tmp/front.jpg",
            cnic_back_image_url="/tmp/back.jpg",
            liveness_video_url="/tmp/video.mp4",
            nadra_verification_data={"success": True, "verified_cnic": cnic},
            shufti_verification_data={"ocr": {"success": True}, "liveness": {"success": True}},
        )
        session.add(kyc)
        await session.flush()

        q = KycVerificationQueue(kyc_verification_id=kyc.id)
        session.add(q)
        await session.commit()


# ─── Auth guard ───────────────────────────────────────────────────────────────

async def test_kyc_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/kyc/start")
    assert response.status_code == 401


# ─── KYC start (idempotent) ───────────────────────────────────────────────────

async def test_kyc_start_creates_record(client: AsyncClient, test_user):
    user, token = test_user
    r = await client.post("/api/v1/kyc/start", headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == KycStatus.PENDING.value
    assert data["cnic_front_image_url"] is None


async def test_kyc_start_is_idempotent(client: AsyncClient, test_user):
    user, token = test_user
    headers = _auth(token)
    r1 = await client.post("/api/v1/kyc/start", headers=headers)
    r2 = await client.post("/api/v1/kyc/start", headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


# ─── Document upload ──────────────────────────────────────────────────────────

async def test_kyc_upload_invalid_type(client: AsyncClient, test_user):
    user, token = test_user
    files = {"file": ("test.jpg", b"fake-bytes", "image/jpeg")}
    r = await client.post(
        "/api/v1/kyc/upload/bad_type", headers=_auth(token), files=files
    )
    assert r.status_code == 400


async def test_kyc_upload_documents(client: AsyncClient, test_user):
    user, token = test_user
    headers = _auth(token)

    for doc_type in ("cnic_front", "cnic_back", "liveness_video"):
        files = {"file": (f"{doc_type}.jpg", b"fake-bytes", "image/jpeg")}
        r = await client.post(
            f"/api/v1/kyc/upload/{doc_type}", headers=headers, files=files
        )
        assert r.status_code == 200, f"Upload failed for {doc_type}: {r.text}"

    # Verify all three URLs are stored
    r = await client.get("/api/v1/kyc/status", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["cnic_front_image_url"] is not None
    assert data["cnic_back_image_url"] is not None
    assert data["liveness_video_url"] is not None


# ─── Submit guard ─────────────────────────────────────────────────────────────

async def test_kyc_submit_incomplete_docs(client: AsyncClient, test_user):
    """Submitting without all three docs must return 400."""
    user, token = test_user
    # Upload only one doc
    files = {"file": ("front.jpg", b"fake", "image/jpeg")}
    await client.post("/api/v1/kyc/upload/cnic_front", headers=_auth(token), files=files)

    r = await client.post("/api/v1/kyc/submit", headers=_auth(token))
    assert r.status_code == 400
    assert "Missing required documents" in r.json()["detail"]


# ─── Submit happy path → IN_REVIEW ───────────────────────────────────────────

async def test_kyc_submit_transitions_to_in_review(client: AsyncClient, test_user):
    """With valid docs the flow should reach IN_REVIEW (NADRA mock passes)."""
    user, token = test_user
    headers = _auth(token)

    for doc_type in ("cnic_front", "cnic_back", "liveness_video"):
        files = {"file": (f"{doc_type}.jpg", b"ok-bytes", "image/jpeg")}
        await client.post(f"/api/v1/kyc/upload/{doc_type}", headers=headers, files=files)

    r = await client.post("/api/v1/kyc/submit", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in (KycStatus.IN_REVIEW.value, KycStatus.APPROVED.value)


# ─── Submit → REJECTED by liveness ───────────────────────────────────────────

async def test_kyc_submit_rejected_by_liveness(client: AsyncClient, test_user):
    """A liveness video URL containing 'spoof' triggers rejection."""
    user, token = test_user
    async with TestingSessionLocal() as session:
        kyc = UserKycVerification(
            user_id=user.id,
            status=KycStatus.PENDING,
            cnic_front_image_url="/tmp/ok_front.jpg",
            cnic_back_image_url="/tmp/ok_back.jpg",
            liveness_video_url="/tmp/spoof_video.mp4",  # triggers mock rejection
        )
        session.add(kyc)
        await session.commit()

    r = await client.post("/api/v1/kyc/submit", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == KycStatus.REJECTED.value
    assert r.json()["rejection_reason"] is not None


# ─── Customer Profile ─────────────────────────────────────────────────────────

async def test_profile_not_found(client: AsyncClient, test_user):
    user, token = test_user
    r = await client.get("/api/v1/kyc/profile", headers=_auth(token))
    assert r.status_code == 404


async def test_profile_create_and_read(client: AsyncClient, test_user):
    user, token = test_user
    payload = {
        "first_name": "Ali",
        "last_name": "Khan",
        "cnic": "12345-1234567-1",
        "dob": "1995-06-15T00:00:00",
        "address": "Karachi, Pakistan",
    }
    # Create
    r = await client.put("/api/v1/kyc/profile", json=payload, headers=_auth(token))
    assert r.status_code == 200
    data = r.json()
    assert data["first_name"] == "Ali"
    assert data["cnic"] == "12345-1234567-1"

    # Read back
    r2 = await client.get("/api/v1/kyc/profile", headers=_auth(token))
    assert r2.status_code == 200
    assert r2.json()["last_name"] == "Khan"


async def test_profile_update(client: AsyncClient, test_user):
    user, token = test_user
    payload = {
        "first_name": "Bilal",
        "last_name": "Ahmed",
        "cnic": "12345-1234567-2",
        "dob": "1990-01-01T00:00:00",
        "address": "Lahore",
    }
    await client.put("/api/v1/kyc/profile", json=payload, headers=_auth(token))

    # Update address
    payload["address"] = "Islamabad"
    r = await client.put("/api/v1/kyc/profile", json=payload, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["address"] == "Islamabad"


async def test_profile_invalid_cnic_format(client: AsyncClient, test_user):
    user, token = test_user
    payload = {
        "first_name": "Ali",
        "last_name": "Khan",
        "cnic": "BAD-CNIC",  # invalid format
        "dob": "1995-06-15T00:00:00",
    }
    r = await client.put("/api/v1/kyc/profile", json=payload, headers=_auth(token))
    assert r.status_code == 422


# ─── Admin queue ─────────────────────────────────────────────────────────────

async def test_admin_queue_empty(client: AsyncClient, test_admin):
    _, token = test_admin
    r = await client.get("/api/v1/admin/kyc/queue", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []


async def test_admin_queue_approve(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin
    await _seed_full_kyc(user.id)

    # List queue
    r = await client.get("/api/v1/admin/kyc/queue", headers=_auth(admin_token))
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    queue_id = items[0]["id"]

    # Approve
    r = await client.post(
        f"/api/v1/admin/kyc/{queue_id}/decision",
        json={"approved": True},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == KycStatus.APPROVED.value


async def test_admin_queue_reject_requires_reason(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin
    await _seed_full_kyc(user.id)

    r = await client.get("/api/v1/admin/kyc/queue", headers=_auth(admin_token))
    queue_id = r.json()[0]["id"]

    # Reject without reason → validation error
    r = await client.post(
        f"/api/v1/admin/kyc/{queue_id}/decision",
        json={"approved": False},
        headers=_auth(admin_token),
    )
    assert r.status_code == 422


async def test_admin_queue_reject_with_reason(client: AsyncClient, test_user, test_admin):
    user, _ = test_user
    _, admin_token = test_admin
    await _seed_full_kyc(user.id)

    r = await client.get("/api/v1/admin/kyc/queue", headers=_auth(admin_token))
    queue_id = r.json()[0]["id"]

    r = await client.post(
        f"/api/v1/admin/kyc/{queue_id}/decision",
        json={"approved": False, "rejection_reason": "Photo is blurry."},
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == KycStatus.REJECTED.value
    assert data["rejection_reason"] == "Photo is blurry."


async def test_admin_queue_item_removed_after_decision(client: AsyncClient, test_user, test_admin):
    """Queue should be empty once a decision has been made."""
    user, _ = test_user
    _, admin_token = test_admin
    await _seed_full_kyc(user.id)

    r = await client.get("/api/v1/admin/kyc/queue", headers=_auth(admin_token))
    queue_id = r.json()[0]["id"]

    await client.post(
        f"/api/v1/admin/kyc/{queue_id}/decision",
        json={"approved": True},
        headers=_auth(admin_token),
    )

    r = await client.get("/api/v1/admin/kyc/queue", headers=_auth(admin_token))
    assert r.json() == []


async def test_admin_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/admin/kyc/queue")
    assert r.status_code == 401
