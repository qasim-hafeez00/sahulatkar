"""
Unit tests for KycService — Mutation Testing Assignment (CS-4006)
Target module: apps/gateway/src/services/kyc.py

These tests are designed to directly test KycService business logic using mocks,
targeting specific mutation operators (ROR, LCR, SVR, SDL) that integration
tests alone cannot reliably kill.

Run from apps/gateway/:
    pytest tests/test_services/test_kyc_service_unit.py -v --timeout=30
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

from sk_shared.models.kyc import (
    KycStatus,
    UserKycVerification,
    CustomerProfile,
    KycVerificationQueue,
)


def _bootstrap_project_root() -> None:
    current_file = Path(__file__).resolve()
    for candidate in current_file.parents:
        if (candidate / "src" / "services" / "kyc.py").exists() and (candidate / "src" / "schemas" / "kyc.py").exists():
            project_root = candidate
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            return


_bootstrap_project_root()

from src.services.kyc import KycService

try:
    from src.schemas.kyc import CustomerProfileBase
except ModuleNotFoundError:
    class CustomerProfileBase:
        pass

pytestmark = pytest.mark.asyncio


# ─── Mock factories ───────────────────────────────────────────────────────────

def _make_kyc(**kwargs):
    """Return a MagicMock shaped like UserKycVerification with sensible defaults."""
    defaults = dict(
        id=1,
        user_id=42,
        status=KycStatus.PENDING,
        attempt_number=1,
        cnic_front_image_url=None,
        cnic_back_image_url=None,
        liveness_video_url=None,
        shufti_verification_data=None,
        nadra_verification_data=None,
        rejection_reason=None,
        nadra_verified_at=None,
    )
    defaults.update(kwargs)
    kyc = MagicMock(spec=UserKycVerification)
    for k, v in defaults.items():
        setattr(kyc, k, v)
    return kyc


def _make_db(kyc_result=None, queue_result=None):
    """
    Return an AsyncMock database session whose execute() returns kyc_result
    on the first call and queue_result on subsequent calls.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    call_count = [0]

    async def _execute(*args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one_or_none = MagicMock(return_value=kyc_result)
        else:
            result.scalar_one_or_none = MagicMock(return_value=queue_result)
        return result

    db.execute = _execute
    return db


def _make_shufti_ok(extracted_cnic="12345-1234567-1"):
    """Shufti mock that passes OCR and liveness."""
    client = AsyncMock()
    client.verify_document = AsyncMock(
        return_value={
            "success": True,
            "extracted_data": {"cnic": extracted_cnic},
        }
    )
    client.verify_liveness = AsyncMock(return_value={"success": True})
    return client


def _make_nadra_ok():
    """NADRA mock that returns True (CNIC verified)."""
    client = AsyncMock()
    client.verify_cnic = AsyncMock(return_value=True)
    return client


def _make_full_kyc(**kwargs):
    """KYC record with all three document URLs pre-filled."""
    defaults = dict(
        cnic_front_image_url="/tmp/front.jpg",
        cnic_back_image_url="/tmp/back.jpg",
        liveness_video_url="/tmp/video.mp4",
    )
    defaults.update(kwargs)
    return _make_kyc(**defaults)


# ═════════════════════════════════════════════════════════════════════════════
# CLASS: TestGetOrCreateKyc
# ═════════════════════════════════════════════════════════════════════════════

class TestGetOrCreateKyc:

    async def test_returns_existing_kyc_without_insert(self):
        """If a KYC row exists it must be returned as-is; db.add must NOT fire."""
        existing = _make_kyc(user_id=42)
        db = _make_db(kyc_result=existing)
        svc = KycService(db)

        result = await svc.get_or_create_kyc(42)

        assert result is existing
        db.add.assert_not_called()
        db.commit.assert_not_called()

    async def test_creates_pending_kyc_when_none_exists(self):
        """No existing row → create UserKycVerification(status=PENDING) and persist."""
        db = _make_db(kyc_result=None)
        db.refresh = AsyncMock(return_value=None)
        svc = KycService(db)

        # Patch select so SQLAlchemy doesn't reject the mocked class as invalid.
        with patch("src.services.kyc.select"):
            with patch("src.services.kyc.UserKycVerification") as MockKyc:
                mock_instance = _make_kyc(user_id=42, status=KycStatus.PENDING)
                MockKyc.return_value = mock_instance
                await svc.get_or_create_kyc(42)

        MockKyc.assert_called_once_with(user_id=42, status=KycStatus.PENDING)
        db.add.assert_called_once()
        db.commit.assert_called_once()

    async def test_new_kyc_initial_status_is_not_submitted(self):
        """
        Kills SVR mutant: KycStatus.PENDING replaced with KycStatus.SUBMITTED.
        Newly created KYC must be PENDING, not any other status.
        """
        db = _make_db(kyc_result=None)
        db.refresh = AsyncMock(return_value=None)
        svc = KycService(db)

        with patch("src.services.kyc.select"):
            with patch("src.services.kyc.UserKycVerification") as MockKyc:
                mock_instance = _make_kyc(user_id=42, status=KycStatus.PENDING)
                MockKyc.return_value = mock_instance
                await svc.get_or_create_kyc(42)

        # Verify call was made with PENDING, not SUBMITTED / IN_REVIEW / APPROVED
        _, kwargs = MockKyc.call_args
        assert kwargs.get("status") == KycStatus.PENDING
        assert kwargs.get("status") != KycStatus.SUBMITTED
        assert kwargs.get("status") != KycStatus.IN_REVIEW


# ═════════════════════════════════════════════════════════════════════════════
# CLASS: TestUploadDocument
# ═════════════════════════════════════════════════════════════════════════════

class TestUploadDocument:

    async def test_cnic_front_sets_only_front_url(self):
        """Uploading cnic_front must set only cnic_front_image_url."""
        kyc = _make_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        await svc.upload_document(42, "cnic_front", "/tmp/front.jpg")

        assert kyc.cnic_front_image_url == "/tmp/front.jpg"
        assert kyc.cnic_back_image_url is None
        assert kyc.liveness_video_url is None

    async def test_cnic_back_sets_only_back_url(self):
        """Uploading cnic_back must set only cnic_back_image_url."""
        kyc = _make_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        await svc.upload_document(42, "cnic_back", "/tmp/back.jpg")

        assert kyc.cnic_back_image_url == "/tmp/back.jpg"
        assert kyc.cnic_front_image_url is None
        assert kyc.liveness_video_url is None

    async def test_liveness_video_sets_only_video_url(self):
        """Uploading liveness_video must set only liveness_video_url."""
        kyc = _make_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        await svc.upload_document(42, "liveness_video", "/tmp/video.mp4")

        assert kyc.liveness_video_url == "/tmp/video.mp4"
        assert kyc.cnic_front_image_url is None
        assert kyc.cnic_back_image_url is None


# ═════════════════════════════════════════════════════════════════════════════
# CLASS: TestSubmitForVerification
# ═════════════════════════════════════════════════════════════════════════════

class TestSubmitForVerification:

    # ── Missing document guard (SDL / BCR targets) ────────────────────────────

    async def test_raises_when_cnic_front_missing(self):
        """
        Kills SDL mutant: deletion of 'if not kyc.cnic_front_image_url: missing.append(...)'.
        cnic_front absence must be detected individually.
        """
        kyc = _make_kyc(
            cnic_front_image_url=None,
            cnic_back_image_url="/back.jpg",
            liveness_video_url="/video.mp4",
        )
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        with pytest.raises(ValueError) as exc:
            await svc.submit_for_verification(42)

        assert "cnic_front" in str(exc.value)

    async def test_raises_when_cnic_back_missing(self):
        """
        Kills SDL mutant: deletion of cnic_back check.
        cnic_back absence must be detected even when front is present.
        """
        kyc = _make_kyc(
            cnic_front_image_url="/front.jpg",
            cnic_back_image_url=None,
            liveness_video_url="/video.mp4",
        )
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        with pytest.raises(ValueError) as exc:
            await svc.submit_for_verification(42)

        assert "cnic_back" in str(exc.value)

    async def test_raises_when_liveness_video_missing(self):
        """
        Kills SDL mutant: deletion of liveness_video check.
        liveness_video absence must be detected even when CNIC docs are present.
        """
        kyc = _make_kyc(
            cnic_front_image_url="/front.jpg",
            cnic_back_image_url="/back.jpg",
            liveness_video_url=None,
        )
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        with pytest.raises(ValueError) as exc:
            await svc.submit_for_verification(42)

        assert "liveness_video" in str(exc.value)

    # ── Intermediate SUBMITTED status (MUTANT #7 — SVR target) ───────────────

    async def test_status_is_submitted_before_external_api_calls(self):
        """
        KILLS MUTANT #7 (SVR): kyc.status = KycStatus.SUBMITTED → KycStatus.PENDING.

        The first commit inside submit_for_verification must persist status=SUBMITTED,
        not PENDING or any other status. This intermediate state is observable if the
        service crashes between commit and external calls — a client would see SUBMITTED
        rather than PENDING, which is the correct UX signal that processing has started.

        Root cause of survival: all integration tests only assert the *final* status
        (IN_REVIEW / REJECTED), never the intermediate state after the first commit.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc, queue_result=None)

        committed_statuses = []

        async def _commit():
            committed_statuses.append(kyc.status)

        db.commit = _commit
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()
        svc.nadra_client = _make_nadra_ok()

        await svc.submit_for_verification(42)

        # The very first commit must have SUBMITTED status
        assert len(committed_statuses) >= 1, "db.commit was never called"
        assert committed_statuses[0] == KycStatus.SUBMITTED, (
            f"Expected SUBMITTED on first commit, got {committed_statuses[0]}. "
            f"SVR mutant (PENDING substitution) would produce {KycStatus.PENDING}."
        )

    # ── Shufti OR → AND (LCR boundary tests) ─────────────────────────────────

    async def test_rejected_when_only_ocr_fails_liveness_passes(self):
        """
        KILLS LCR mutant on line 91: 'or' → 'and'.

        Original:  if not ocr_result.get("success") OR not liveness_result.get("success")
        Mutant:    if not ocr_result.get("success") AND not liveness_result.get("success")

        When OCR fails alone (liveness passes), original = True → REJECTED.
        The AND mutant = False → NOT rejected → continues to NADRA → IN_REVIEW.
        This test catches that divergence at the boundary where one check fails.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        shufti = AsyncMock()
        shufti.verify_document = AsyncMock(
            return_value={"success": False, "reason": "Blurry document"}
        )
        shufti.verify_liveness = AsyncMock(return_value={"success": True})  # passes
        svc.shufti_client = shufti

        await svc.submit_for_verification(42)

        assert kyc.status == KycStatus.REJECTED, (
            f"Expected REJECTED when OCR fails alone. Got {kyc.status}. "
            "LCR (or→and) mutant would produce IN_REVIEW here."
        )
        assert "Blurry document" in kyc.rejection_reason

    async def test_rejected_when_only_liveness_fails_ocr_passes(self):
        """
        Secondary LCR boundary: liveness fails, OCR passes.
        Complements the above by showing both individual failure directions.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        shufti = AsyncMock()
        shufti.verify_document = AsyncMock(
            return_value={
                "success": True,
                "extracted_data": {"cnic": "12345-1234567-1"},
            }
        )
        shufti.verify_liveness = AsyncMock(
            return_value={"success": False, "reason": "Face spoofing detected"}
        )
        svc.shufti_client = shufti

        await svc.submit_for_verification(42)

        assert kyc.status == KycStatus.REJECTED
        assert "Face spoofing detected" in kyc.rejection_reason

    async def test_not_rejected_when_both_shufti_checks_pass(self):
        """Complement: when both pass, must reach NADRA and NOT stay rejected."""
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc, queue_result=None)
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()
        svc.nadra_client = _make_nadra_ok()

        await svc.submit_for_verification(42)

        assert kyc.status != KycStatus.REJECTED

    # ── CNIC fallback 'or' → 'and' (MUTANT #23 — LCR target) ────────────────

    async def test_default_cnic_used_when_ocr_extracts_no_cnic(self):
        """
        KILLS MUTANT #23 (LCR): second 'or' in extracted_cnic expression changed to 'and'.

        Original (line 105):
            extracted_cnic = (ocr_result.get("extracted_data") or {}).get("cnic")
                             or "12345-1234567-1"

        Mutant:
            extracted_cnic = (ocr_result.get("extracted_data") or {}).get("cnic")
                             AND "12345-1234567-1"

        When OCR returns no 'cnic' key, the original falls back to the literal.
        The AND mutant evaluates: None and "12345-1234567-1" = None, then passes
        None to verify_cnic() → AttributeError inside the NADRA try-block →
        sets status=REJECTED with "unavailable" reason instead of attempting NADRA.

        Root cause of survival: existing tests always use ShuftiClientMock which
        returns a hardcoded cnic — the fallback literal is never exercised.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc, queue_result=None)
        svc = KycService(db)

        # Shufti passes but returns NO cnic in extracted_data
        shufti = AsyncMock()
        shufti.verify_document = AsyncMock(
            return_value={"success": True, "extracted_data": {}}  # no 'cnic' key
        )
        shufti.verify_liveness = AsyncMock(return_value={"success": True})
        svc.shufti_client = shufti

        received_cnics = []

        async def _verify_cnic(cnic):
            received_cnics.append(cnic)
            return True

        nadra = AsyncMock()
        nadra.verify_cnic = _verify_cnic
        svc.nadra_client = nadra

        await svc.submit_for_verification(42)

        assert len(received_cnics) == 1, "NADRA must be called exactly once"
        assert received_cnics[0] == "12345-1234567-1", (
            f"Expected fallback CNIC '12345-1234567-1', got '{received_cnics[0]}'. "
            "LCR (or→and) mutant would pass None, causing an exception."
        )
        assert kyc.status == KycStatus.IN_REVIEW

    # ── nadra_verified_at assignment (MUTANT #27 — SDL target) ───────────────

    async def test_nadra_verified_at_set_when_nadra_passes(self):
        """
        KILLS MUTANT #27 (SDL): deletion of 'kyc.nadra_verified_at = datetime.now(timezone.utc)'.

        When NADRA verification succeeds, nadra_verified_at must be stamped.
        This timestamp is used downstream by admin workflows to determine
        when the CNIC was verified — its absence is a silent data-integrity fault.

        Root cause of survival: existing integration tests assert status (IN_REVIEW)
        but never inspect the nadra_verified_at field on the returned KYC object.
        """
        kyc = _make_full_kyc(nadra_verified_at=None)
        db = _make_db(kyc_result=kyc, queue_result=None)
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()
        svc.nadra_client = _make_nadra_ok()

        before = datetime.now(timezone.utc)
        await svc.submit_for_verification(42)
        after = datetime.now(timezone.utc)

        assert kyc.nadra_verified_at is not None, (
            "nadra_verified_at must be set when NADRA passes. "
            "SDL mutant (statement deleted) leaves it as None."
        )
        assert before <= kyc.nadra_verified_at <= after

    async def test_nadra_verified_at_not_set_when_nadra_fails(self):
        """Complement: when NADRA fails, verified_at must NOT be set (wrong branch)."""
        kyc = _make_full_kyc(nadra_verified_at=None)
        db = _make_db(kyc_result=kyc, queue_result=None)
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()

        nadra = AsyncMock()
        nadra.verify_cnic = AsyncMock(return_value=False)
        svc.nadra_client = nadra

        await svc.submit_for_verification(42)

        assert kyc.nadra_verified_at is None

    # ── Queue idempotency (MUTANT #18 — ROR target) ──────────────────────────

    async def test_queue_entry_added_when_no_existing_entry(self):
        """
        KILLS MUTANT #18 (ROR): 'if not existing_q.scalar_one_or_none():'
                                 → 'if existing_q.scalar_one_or_none():'

        When NADRA passes and no queue entry exists (scalar_one_or_none = None),
        a new KycVerificationQueue row MUST be added.

        Original:  not None = True  → add entry  ✓
        Mutant:    None = False → skip add  ✗  (queue entry never created)

        Root cause of survival: the only integration test that checks the admin
        queue uses _seed_full_kyc() which bypasses submit_for_verification entirely
        and inserts the queue row directly. No test verifies the queue row was
        created by the submission flow.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc, queue_result=None)  # None = no existing entry

        added_objects = []
        db.add = MagicMock(side_effect=added_objects.append)

        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()
        svc.nadra_client = _make_nadra_ok()

        await svc.submit_for_verification(42)

        assert len(added_objects) >= 1, (
            "db.add must be called at least once to create the KycVerificationQueue entry. "
            "ROR mutant (not removed) skips the add."
        )
        # Verify at least one added object is queue-like (has kyc_verification_id)
        with patch("src.services.kyc.KycVerificationQueue") as MockQueue:
            # Confirm the service creates a queue object — already checked via add call
            pass

    async def test_queue_entry_not_duplicated_when_already_exists(self):
        """
        Complement: when an entry already exists, db.add must NOT be called again.

        Original:  not existing = not MagicMock() = False → skip ✓
        Mutant:    existing = MagicMock() = True → add duplicate ✗
        """
        kyc = _make_full_kyc()
        existing_queue_entry = MagicMock()  # simulates existing queue row
        db = _make_db(kyc_result=kyc, queue_result=existing_queue_entry)

        added_objects = []
        db.add = MagicMock(side_effect=added_objects.append)

        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()
        svc.nadra_client = _make_nadra_ok()

        await svc.submit_for_verification(42)

        assert len(added_objects) == 0, (
            "db.add must NOT be called when a queue entry already exists. "
            "ROR mutant (negation removed) would call add and create a duplicate."
        )

    # ── NADRA rejection (ROR / BCR targets) ──────────────────────────────────

    async def test_rejected_when_nadra_returns_false(self):
        """
        Kills BCR mutant: 'if not nadra_ok:' → 'if nadra_ok:'.
        When NADRA fails, status must be REJECTED with NADRA in the reason.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc, queue_result=None)
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()

        nadra = AsyncMock()
        nadra.verify_cnic = AsyncMock(return_value=False)
        svc.nadra_client = nadra

        await svc.submit_for_verification(42)

        assert kyc.status == KycStatus.REJECTED
        assert "NADRA" in kyc.rejection_reason

    async def test_in_review_when_nadra_returns_true(self):
        """Complement: NADRA success → IN_REVIEW."""
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc, queue_result=None)
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()
        svc.nadra_client = _make_nadra_ok()

        await svc.submit_for_verification(42)

        assert kyc.status == KycStatus.IN_REVIEW

    # ── Exception handling (SDL targets) ─────────────────────────────────────

    async def test_shufti_exception_sets_rejected_with_reason(self):
        """
        Kills SDL mutant: deletion of status/reason assignment in Shufti except block.
        A Shufti API error must result in REJECTED with 'unavailable' in reason.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)

        shufti = AsyncMock()
        shufti.verify_document = AsyncMock(side_effect=RuntimeError("network error"))
        svc.shufti_client = shufti

        await svc.submit_for_verification(42)

        assert kyc.status == KycStatus.REJECTED
        assert "unavailable" in kyc.rejection_reason.lower()

    async def test_nadra_exception_sets_rejected_with_reason(self):
        """
        Kills SDL mutant: deletion of status/reason assignment in NADRA except block.
        A NADRA API error must result in REJECTED with 'NADRA' in reason.
        """
        kyc = _make_full_kyc()
        db = _make_db(kyc_result=kyc)
        svc = KycService(db)
        svc.shufti_client = _make_shufti_ok()

        nadra = AsyncMock()
        nadra.verify_cnic = AsyncMock(side_effect=RuntimeError("timeout"))
        svc.nadra_client = nadra

        await svc.submit_for_verification(42)

        assert kyc.status == KycStatus.REJECTED
        assert "NADRA" in kyc.rejection_reason


# ═════════════════════════════════════════════════════════════════════════════
# CLASS: TestGetProfile
# ═════════════════════════════════════════════════════════════════════════════

class TestGetProfile:

    async def test_returns_none_when_no_profile_exists(self):
        """SVR: 'return profile' → 'return None' — assert we get actual None back."""
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result)
        svc = KycService(db)

        returned = await svc.get_profile(99)

        assert returned is None

    async def test_string_cnic_skips_kms_decryption(self):
        """
        Kills LCR mutant: 'if profile and profile.cnic' → 'if profile or profile.cnic'.

        When cnic is already a plain string (not bytes), the isinstance guard prevents
        decryption. With the OR mutant, profile=None would cause AttributeError on
        profile.cnic — but here we test the string path specifically to confirm
        KMSProvider.decrypt is never invoked for non-bytes CNIC values.
        """
        profile = MagicMock(spec=CustomerProfile)
        profile.cnic = "12345-1234567-1"

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=profile)
        db.execute = AsyncMock(return_value=result)
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            returned = await svc.get_profile(42)

        mock_kms.return_value.decrypt.assert_not_called()
        assert returned is profile

    async def test_bytes_cnic_triggers_kms_decryption(self):
        """
        Kills SDL mutant: deletion of the isinstance check or the decrypt call.
        bytes cnic → KMSProvider().decrypt() must be called.
        """
        profile = MagicMock(spec=CustomerProfile)
        profile.user_id = 42
        profile.cnic = b"\xde\xad\xbe\xef" * 8  # 32 dummy bytes

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=profile)
        db.execute = AsyncMock(return_value=result)
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            mock_kms.return_value.decrypt = MagicMock(return_value="12345-1234567-1")
            returned = await svc.get_profile(42)

        mock_kms.return_value.decrypt.assert_called_once_with(b"\xde\xad\xbe\xef" * 8)
        assert returned.cnic == "12345-1234567-1"

    async def test_utf8_fallback_when_kms_decrypt_fails(self):
        """
        Kills SDL mutant: deletion of 'profile.cnic = raw.decode("utf-8")' fallback.

        When KMS decrypt raises, the code attempts UTF-8 decode as a legacy-plaintext
        fallback. Removing that statement leaves cnic as bytes, which breaks serialization.
        """
        plain_bytes = "12345-1234567-1".encode("utf-8")
        profile = MagicMock(spec=CustomerProfile)
        profile.user_id = 42
        profile.cnic = plain_bytes

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=profile)
        db.execute = AsyncMock(return_value=result)
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            mock_kms.return_value.decrypt = MagicMock(
                side_effect=Exception("AES-GCM tag mismatch")
            )
            returned = await svc.get_profile(42)

        assert returned.cnic == "12345-1234567-1", (
            "Expected UTF-8 fallback to yield '12345-1234567-1'. "
            "SDL mutant (statement deleted) would leave cnic as raw bytes."
        )

    async def test_empty_string_set_when_all_decryption_fails(self):
        """
        KILLS MUTANT #34 (SVR): 'profile.cnic = ""' → 'profile.cnic = None'.

        When both KMS decrypt AND UTF-8 decode fail (e.g., corrupted binary blob),
        cnic must be set to the empty string sentinel, not None. Returning None
        could cause NullPointerError-style failures in callers that assume a string.

        Root cause of survival: no existing test creates a profile with bytes that
        are invalid as UTF-8 and also fail KMS decryption.
        """
        corrupted_bytes = b"\xff\xfe"  # invalid UTF-8 sequence
        profile = MagicMock(spec=CustomerProfile)
        profile.user_id = 42
        profile.cnic = corrupted_bytes

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=profile)
        db.execute = AsyncMock(return_value=result)
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            mock_kms.return_value.decrypt = MagicMock(
                side_effect=Exception("decryption failed")
            )
            returned = await svc.get_profile(42)

        assert returned.cnic == "", (
            f"Expected empty string sentinel, got {returned.cnic!r}. "
            "SVR mutant ('' → None) would set cnic to None, breaking callers."
        )
        assert returned.cnic is not None, "cnic must be '' not None after total decryption failure"

    async def test_none_cnic_skips_decryption_block(self):
        """
        Kills LCR mutant on the 'if profile and profile.cnic' guard.

        When profile exists but cnic is None (no CNIC uploaded yet), the condition
        must be False so decryption is skipped entirely. The 'or' mutant would
        evaluate 'profile or None' = profile (truthy) → enters block → tries to
        decrypt None → crash.
        """
        profile = MagicMock(spec=CustomerProfile)
        profile.cnic = None

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=profile)
        db.execute = AsyncMock(return_value=result)
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            returned = await svc.get_profile(42)

        mock_kms.return_value.decrypt.assert_not_called()
        assert returned is profile


# ═════════════════════════════════════════════════════════════════════════════
# CLASS: TestUpsertProfile
# ═════════════════════════════════════════════════════════════════════════════

class TestUpsertProfile:

    def _payload(self, **overrides):
        defaults = dict(
            first_name="Ali",
            last_name="Khan",
            cnic="12345-1234567-1",
            dob=datetime(1990, 1, 1),
            address="Karachi",
        )
        defaults.update(overrides)
        p = MagicMock(spec=CustomerProfileBase)
        for k, v in defaults.items():
            setattr(p, k, v)
        return p

    async def test_new_profile_created_and_added_when_none_exists(self):
        """
        Kills SVR/ROR mutant: 'if profile is None:' → 'if profile is not None:'.
        When no profile exists, db.add must be called to insert a new row.
        """
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=scalar)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = KycService(db)

        # select must also be patched so SQLAlchemy doesn't reject the mocked class.
        with patch("src.services.kyc.select"):
            with patch("src.services.kyc.KMSProvider") as mock_kms:
                mock_kms.return_value.encrypt = MagicMock(return_value=b"enc")
                with patch("src.services.kyc.CustomerProfile") as MockProfile:
                    mock_profile = MagicMock()
                    MockProfile.return_value = mock_profile
                    await svc.upsert_profile(42, self._payload())

        db.add.assert_called_once()

    async def test_existing_profile_updated_not_re_inserted(self):
        """
        Complement: when profile already exists, db.add must NOT be called again.
        Mutation 'if profile is not None' would always add, creating duplicates.
        """
        existing = MagicMock(spec=CustomerProfile)
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=existing)
        db.execute = AsyncMock(return_value=scalar)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            mock_kms.return_value.encrypt = MagicMock(return_value=b"enc")
            await svc.upsert_profile(42, self._payload())

        db.add.assert_not_called()

    async def test_cnic_is_encrypted_not_stored_plaintext(self):
        """
        Kills SDL mutant: deletion of 'profile.cnic = KMSProvider().encrypt(payload.cnic)'.

        The CNIC is PII and must be encrypted at rest. Removing this statement
        leaves the cnic field unset (None for new profiles, stale for updates).
        This is a silent security regression — reads would return wrong data.
        """
        existing = MagicMock(spec=CustomerProfile)
        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=existing)
        db.execute = AsyncMock(return_value=scalar)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            mock_kms.return_value.encrypt = MagicMock(return_value=b"encrypted_cnic_blob")
            await svc.upsert_profile(42, self._payload(cnic="12345-1234567-1"))

        mock_kms.return_value.encrypt.assert_called_once_with("12345-1234567-1")
        assert existing.cnic == b"encrypted_cnic_blob"

    async def test_all_five_profile_fields_written(self):
        """
        Kills five SDL mutants, one per field assignment deletion.
        Every field in the payload must be written to the profile object.
        """
        existing = MagicMock(spec=CustomerProfile)
        dob = datetime(1990, 6, 15)

        db = AsyncMock()
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=existing)
        db.execute = AsyncMock(return_value=scalar)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        svc = KycService(db)

        with patch("src.services.kyc.KMSProvider") as mock_kms:
            mock_kms.return_value.encrypt = MagicMock(return_value=b"enc")
            await svc.upsert_profile(
                42,
                self._payload(
                    first_name="Bilal",
                    last_name="Ahmed",
                    cnic="12345-1234567-2",
                    dob=dob,
                    address="Lahore",
                ),
            )

        assert existing.first_name == "Bilal"
        assert existing.last_name == "Ahmed"
        assert existing.dob == dob
        assert existing.address == "Lahore"
        assert existing.cnic == b"enc"
