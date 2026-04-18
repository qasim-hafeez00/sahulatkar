from __future__ import annotations

from datetime import date
import json

import httpx
import pytest

from src.config import settings
from src.services.tasdeeq_service import TasdeeqService


@pytest.mark.asyncio
async def test_tasdeeq_batch_mode_writes_outbox_and_audit(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "tasdeeq_mode", "batch_csv")
    monkeypatch.setattr(settings, "tasdeeq_audit_dir", str(tmp_path))

    service = TasdeeqService(db_session)

    async def _fake_rows():
        return [
            {
                "loan_id": "L-100",
                "user_id": 100,
                "cnic": "42101-1234567-1",
                "principal": 10000.0,
                "outstanding": 7800.0,
                "status": "active",
                "installments_paid": 1,
                "total_installments": 4,
                "last_payment_date": "2026-04-01T00:00:00+00:00",
            }
        ]

    monkeypatch.setattr(service, "_fetch_report_rows", _fake_rows)

    result = await service.run_reporting_cycle(as_of_date=date(2026, 4, 16))
    assert result["status"] == "submitted_local"
    assert result["attempts"] == 1
    assert result["record_count"] == 1
    assert result["report_path"] is not None

    report_file = tmp_path / "outbox"
    assert report_file.exists()
    assert any(path.suffix == ".csv" for path in report_file.iterdir())

    audit_file = tmp_path / "tasdeeq_submissions.jsonl"
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "submitted_local"
    assert payload["report_date"] == "2026-04-16"


@pytest.mark.asyncio
async def test_tasdeeq_http_mode_retries_and_succeeds(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "tasdeeq_mode", "http")
    monkeypatch.setattr(settings, "tasdeeq_endpoint_url", "https://tasdeeq.example/report")
    monkeypatch.setattr(settings, "tasdeeq_api_token", "token-123")
    monkeypatch.setattr(settings, "tasdeeq_timeout_seconds", 5)
    monkeypatch.setattr(settings, "tasdeeq_max_retries", 3)
    monkeypatch.setattr(settings, "tasdeeq_audit_dir", str(tmp_path))

    service = TasdeeqService(db_session)

    async def _fake_rows():
        return [
            {
                "loan_id": "L-200",
                "user_id": 200,
                "cnic": "42101-7654321-0",
                "principal": 12000.0,
                "outstanding": 9000.0,
                "status": "active",
                "installments_paid": 0,
                "total_installments": 4,
                "last_payment_date": "N/A",
            }
        ]

    monkeypatch.setattr(service, "_fetch_report_rows", _fake_rows)

    call_count = {"value": 0}

    async def _fake_post(self, url, content=None, headers=None):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise httpx.ConnectError("temporary connect failure", request=httpx.Request("POST", url))
        return httpx.Response(200, json={"submission_id": "sub-789"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    result = await service.run_reporting_cycle(as_of_date=date(2026, 4, 16))
    assert result["status"] == "submitted_remote"
    assert result["attempts"] == 2
    assert result["remote_reference"] == "sub-789"

    audit_file = tmp_path / "tasdeeq_submissions.jsonl"
    assert audit_file.exists()
    payload = json.loads(audit_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["status"] == "submitted_remote"
    assert payload["attempts"] == 2
