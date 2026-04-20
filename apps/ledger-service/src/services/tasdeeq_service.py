from __future__ import annotations

import asyncio
import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sk_shared.models.kyc import CustomerProfile
from sk_shared.models.payment import Loan
from src.config import settings
from src.services.tasdeeq_validation import TASDEEQReportRow, TASDEEQCSVValidator, TASDEEQValidationError


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TasdeeqSubmissionResult:
    status: str
    attempts: int
    report_path: str | None = None
    remote_reference: str | None = None
    error: str | None = None


class TasdeeqService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def run_reporting_cycle(self, as_of_date: date | None = None) -> dict[str, Any]:
        report_date = as_of_date or date.today()
        csv_content, records = await self.build_report_csv(report_date=report_date)
        submission = await self.submit_report(csv_content=csv_content, report_date=report_date, record_count=records)
        return {
            "report_date": report_date.isoformat(),
            "record_count": records,
            "bytes": len(csv_content.encode("utf-8")),
            "status": submission.status,
            "attempts": submission.attempts,
            "report_path": submission.report_path,
            "remote_reference": submission.remote_reference,
            "error": submission.error,
        }

    async def build_report_csv(self, report_date: date) -> tuple[str, int]:
        """
        Build TASDEEQ CSV report with full schema validation.
        
        Fetches all active loans, builds report rows, validates against TASDEEQ schema,
        and generates CSV output.
        
        Raises:
            TASDEEQValidationError: If validation fails
        """
        raw_rows = await self._fetch_report_rows()
        
        # Convert raw data rows to validated TASDEEQReportRow objects
        validated_rows: list[TASDEEQReportRow] = []
        for row_data in raw_rows:
            validated_row = TASDEEQReportRow(
                report_date=report_date,
                loan_id=row_data["loan_id"],
                user_id=row_data["user_id"],
                cnic=row_data["cnic"],
                principal=Decimal(str(row_data["principal"])),
                outstanding=Decimal(str(row_data["outstanding"])),
                status=row_data["status"],
                installments_paid=row_data["installments_paid"],
                total_installments=row_data["total_installments"],
                last_payment_date=row_data["last_payment_date"],
            )
            validated_rows.append(validated_row)
        
        # Validate entire report structure
        validation_stats = TASDEEQCSVValidator.validate_report(validated_rows)
        logger.info(
            "TASDEEQ report validated",
            extra={
                "total_rows": validation_stats["total_rows"],
                "valid_rows": validation_stats["valid_rows"],
                "errors": validation_stats["errors"],
            }
        )
        
        # Generate CSV from validated rows
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(TASDEEQCSVValidator.get_csv_header())
        
        for validated_row in validated_rows:
            writer.writerow(validated_row.to_csv_row())
        
        return output.getvalue(), len(validated_rows)

    async def submit_report(self, *, csv_content: str, report_date: date, record_count: int) -> TasdeeqSubmissionResult:
        mode = settings.tasdeeq_mode.strip().lower()
        if mode in {"batch_csv", "file", "local_file"}:
            result = await self._submit_local_file(csv_content=csv_content, report_date=report_date)
            await self._append_audit_record(
                {
                    "submitted_at": self._utc_now().isoformat(),
                    "mode": mode,
                    "report_date": report_date.isoformat(),
                    "record_count": record_count,
                    "status": result.status,
                    "attempts": result.attempts,
                    "report_path": result.report_path,
                    "remote_reference": result.remote_reference,
                    "error": result.error,
                }
            )
            return result

        if mode in {"http", "api", "api_push"}:
            result = await self._submit_http(csv_content=csv_content, report_date=report_date)
            await self._append_audit_record(
                {
                    "submitted_at": self._utc_now().isoformat(),
                    "mode": mode,
                    "report_date": report_date.isoformat(),
                    "record_count": record_count,
                    "status": result.status,
                    "attempts": result.attempts,
                    "report_path": result.report_path,
                    "remote_reference": result.remote_reference,
                    "error": result.error,
                }
            )
            return result

        raise ValueError("INVALID_TASDEEQ_MODE")

    async def _submit_local_file(self, *, csv_content: str, report_date: date) -> TasdeeqSubmissionResult:
        outbox_dir = Path(settings.tasdeeq_audit_dir) / "outbox"
        outbox_dir.mkdir(parents=True, exist_ok=True)
        timestamp = self._utc_now().strftime("%Y%m%dT%H%M%SZ")
        report_path = outbox_dir / f"tasdeeq_{report_date.isoformat()}_{timestamp}.csv"
        report_path.write_text(csv_content, encoding="utf-8", newline="")
        logger.info("TASDEEQ report staged locally", extra={"report_path": str(report_path)})
        return TasdeeqSubmissionResult(status="submitted_local", attempts=1, report_path=str(report_path))

    async def _submit_http(self, *, csv_content: str, report_date: date) -> TasdeeqSubmissionResult:
        endpoint = settings.tasdeeq_endpoint_url.strip()
        if not endpoint:
            return TasdeeqSubmissionResult(status="failed", attempts=0, error="TASDEEQ_ENDPOINT_NOT_CONFIGURED")

        max_retries = max(1, int(settings.tasdeeq_max_retries))
        timeout = max(1, int(settings.tasdeeq_timeout_seconds))
        payload = csv_content.encode("utf-8")
        headers = {
            "Content-Type": "text/csv",
            "X-Report-Date": report_date.isoformat(),
        }
        if settings.tasdeeq_api_token:
            headers["Authorization"] = f"Bearer {settings.tasdeeq_api_token}"

        attempts = 0
        last_error: str | None = None
        for attempt in range(1, max_retries + 1):
            attempts = attempt
            try:
                async with httpx.AsyncClient(timeout=float(timeout)) as client:
                    response = await client.post(endpoint, content=payload, headers=headers)

                if 200 <= response.status_code < 300:
                    remote_reference = self._extract_remote_reference(response)
                    return TasdeeqSubmissionResult(
                        status="submitted_remote",
                        attempts=attempts,
                        remote_reference=remote_reference,
                    )

                last_error = f"HTTP_{response.status_code}"
                if response.status_code < 500:
                    break
            except httpx.HTTPError as exc:
                last_error = str(exc)

            if attempt < max_retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))

        return TasdeeqSubmissionResult(status="failed", attempts=attempts, error=last_error or "UNKNOWN_ERROR")

    def _extract_remote_reference(self, response: httpx.Response) -> str | None:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                for key in ("submission_id", "reference", "id"):
                    value = payload.get(key)
                    if value:
                        return str(value)
        except ValueError:
            pass
        ref_header = response.headers.get("X-Submission-Id")
        return ref_header or None

    async def _append_audit_record(self, record: dict[str, Any]) -> None:
        audit_dir = Path(settings.tasdeeq_audit_dir)
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / "tasdeeq_submissions.jsonl"
        with audit_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), default=str))
            handle.write("\n")

    async def _fetch_report_rows(self) -> list[dict[str, Any]]:
        stmt = select(Loan).options(selectinload(Loan.installments)).where(Loan.deleted_at.is_(None))
        loans = (await self.db.execute(stmt)).scalars().all()
        if not loans:
            return []

        user_ids = sorted({int(loan.user_id) for loan in loans})
        profiles_stmt = select(CustomerProfile).where(CustomerProfile.user_id.in_(user_ids), CustomerProfile.deleted_at.is_(None))
        profiles = (await self.db.execute(profiles_stmt)).scalars().all()
        profile_map = {int(profile.user_id): profile for profile in profiles}

        rows: list[dict[str, Any]] = []
        for loan in loans:
            profile = profile_map.get(int(loan.user_id))
            paid_count = sum(1 for installment in loan.installments if installment.status == "paid")
            last_payment = max((installment.paid_at for installment in loan.installments if installment.paid_at), default=None)
            rows.append(
                {
                    "loan_id": loan.loan_number,
                    "user_id": int(loan.user_id),
                    "cnic": profile.cnic if profile and profile.cnic else "N/A",
                    "principal": float(loan.principal_amount),
                    "outstanding": float(loan.total_outstanding),
                    "status": loan.status,
                    "installments_paid": paid_count,
                    "total_installments": int(loan.installment_count),
                    "last_payment_date": last_payment.isoformat() if last_payment else "N/A",
                }
            )
        return rows

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)
