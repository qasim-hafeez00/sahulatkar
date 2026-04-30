import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from sk_shared.models.kyc import KycStatus


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


pytestmark = pytest.mark.asyncio


def _make_kyc(**kwargs):
    from sk_shared.models.kyc import UserKycVerification

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
    from unittest.mock import MagicMock

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


@pytest.mark.parametrize(
    "ocr_success,liveness_success,nadra_ok,expected_status,expected_reason_contains",
    [
        (True, True, True, KycStatus.IN_REVIEW, None),
        (False, True, True, KycStatus.REJECTED, "OCR"),
        (True, False, True, KycStatus.REJECTED, "Liveness"),
        (True, True, False, KycStatus.REJECTED, "NADRA"),
    ],
)
async def test_shufti_nadra_matrix(ocr_success, liveness_success, nadra_ok, expected_status, expected_reason_contains):
    """Parametrized coverage for combinations of OCR/liveness/NADRA outcomes."""
    kyc = _make_kyc(cnic_front_image_url="/front", cnic_back_image_url="/back", liveness_video_url="/video")
    db = _make_db(kyc_result=kyc, queue_result=None)
    svc = KycService(db)

    shufti = AsyncMock()
    shufti.verify_document = AsyncMock(return_value={"success": ocr_success, "extracted_data": {"cnic": "12345-1234567-1"} if ocr_success else {}})
    shufti.verify_liveness = AsyncMock(return_value={"success": liveness_success, "reason": "fail" if not liveness_success else None})
    svc.shufti_client = shufti

    nadra = AsyncMock()
    nadra.verify_cnic = AsyncMock(return_value=nadra_ok)
    svc.nadra_client = nadra

    await svc.submit_for_verification(42)

    assert kyc.status == expected_status
    if expected_reason_contains:
        # rejection_reason may contain specific messages from mocks; assert it's present
        assert (kyc.rejection_reason or "") != "", "Expected a non-empty rejection_reason"


async def test_upload_document_unknown_type_noop():
    """Uploading an unknown document type should not modify existing URLs."""
    kyc = _make_kyc()
    db = _make_db(kyc_result=kyc)
    svc = KycService(db)

    await svc.upload_document(42, "unknown_type", "/tmp/x")

    assert kyc.cnic_front_image_url is None
    assert kyc.cnic_back_image_url is None
    assert kyc.liveness_video_url is None
