from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.config import settings
from src.services.tasdeeq_service import TasdeeqService
from src.workers import tasdeeq_worker


class _SessionContextManager:
    """Wraps an already-open AsyncSession so `async with SessionLocal() as
    session:` (as used by every worker's main()) yields the test's real
    db_session instead of opening a connection to the production database
    configured in src.core.database.SessionLocal."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _patch_session(monkeypatch, module, session) -> None:
    monkeypatch.setattr(module, "SessionLocal", lambda: _SessionContextManager(session))


@pytest.mark.asyncio
async def test_main_runs_reporting_cycle_and_writes_outbox_and_audit(db_session, monkeypatch, tmp_path):
    _patch_session(monkeypatch, tasdeeq_worker, db_session)
    monkeypatch.setattr(settings, "tasdeeq_mode", "batch_csv")
    monkeypatch.setattr(settings, "tasdeeq_audit_dir", str(tmp_path))

    async def _fake_rows(self):
        return [
            {
                "loan_id": "L-500",
                "user_id": 500,
                "cnic": "42101-1111111-1",
                "principal": 5000.0,
                "outstanding": 2500.0,
                "status": "active",
                "installments_paid": 2,
                "total_installments": 4,
                "last_payment_date": "N/A",
            }
        ]

    monkeypatch.setattr(TasdeeqService, "_fetch_report_rows", _fake_rows)

    await tasdeeq_worker.main()

    outbox = tmp_path / "outbox"
    assert outbox.exists()
    csv_files = [p for p in outbox.iterdir() if p.suffix == ".csv"]
    assert len(csv_files) == 1

    audit_file = tmp_path / "tasdeeq_submissions.jsonl"
    assert audit_file.exists()
    payload = json.loads(audit_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["record_count"] == 1
    assert payload["status"] == "submitted_local"


@pytest.mark.asyncio
async def test_main_with_no_active_loans_still_submits_header_only_report(db_session, monkeypatch, tmp_path):
    """Edge case: an empty loan book must still produce a valid (header-only)
    CSV submission rather than erroring out or skipping the run."""
    _patch_session(monkeypatch, tasdeeq_worker, db_session)
    monkeypatch.setattr(settings, "tasdeeq_mode", "batch_csv")
    monkeypatch.setattr(settings, "tasdeeq_audit_dir", str(tmp_path))
    # No loans/customer profiles seeded -- exercises the real (unmocked)
    # _fetch_report_rows() against a genuinely empty `loans` table.

    await tasdeeq_worker.main()

    outbox = tmp_path / "outbox"
    csv_files = list(outbox.iterdir())
    assert len(csv_files) == 1
    content = csv_files[0].read_text(encoding="utf-8")
    assert len(content.strip().splitlines()) == 1  # header row only, no data rows

    audit_file = tmp_path / "tasdeeq_submissions.jsonl"
    payload = json.loads(audit_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["record_count"] == 0
    assert payload["status"] == "submitted_local"


@pytest.mark.asyncio
async def test_main_propagates_error_for_unconfigured_mode(db_session, monkeypatch, tmp_path):
    """submit_report() raises ValueError for an unrecognized tasdeeq_mode;
    main() has no try/except around the service call, so this must surface
    (not be silently swallowed) so the process exits non-zero and gets
    noticed by whatever supervises the cron/worker."""
    _patch_session(monkeypatch, tasdeeq_worker, db_session)
    monkeypatch.setattr(settings, "tasdeeq_mode", "unsupported-mode")
    monkeypatch.setattr(settings, "tasdeeq_audit_dir", str(tmp_path))

    with pytest.raises(ValueError, match="INVALID_TASDEEQ_MODE"):
        await tasdeeq_worker.main()


@pytest.mark.asyncio
async def test_main_http_mode_records_failure_after_exhausting_retries(db_session, monkeypatch, tmp_path):
    """Retry/backoff edge case: every HTTP attempt fails with a transient
    connection error. The worker must not crash -- it records a 'failed'
    submission in the audit log after exhausting tasdeeq_max_retries."""
    _patch_session(monkeypatch, tasdeeq_worker, db_session)
    monkeypatch.setattr(settings, "tasdeeq_mode", "http")
    monkeypatch.setattr(settings, "tasdeeq_endpoint_url", "https://tasdeeq.example/report")
    monkeypatch.setattr(settings, "tasdeeq_max_retries", 2)
    monkeypatch.setattr(settings, "tasdeeq_timeout_seconds", 1)
    monkeypatch.setattr(settings, "tasdeeq_audit_dir", str(tmp_path))

    async def _fake_rows(self):
        return []

    monkeypatch.setattr(TasdeeqService, "_fetch_report_rows", _fake_rows)

    async def _always_fail(self, url, content=None, headers=None):
        raise httpx.ConnectError("down", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _always_fail)

    async def _fast_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)

    await tasdeeq_worker.main()  # must not raise -- failure is recorded, not propagated

    audit_file = tmp_path / "tasdeeq_submissions.jsonl"
    payload = json.loads(audit_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["status"] == "failed"
    assert payload["attempts"] == 2
