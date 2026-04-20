"""
TASDEEQ CSV Format Validation

Validates that generated CSV reports conform to the Pakistan TASDEEQ credit bureau schema.
This module enforces strict column structure, data types, and required fields.

Reference: TASDEEQ Bureau CSV Submission Specification v2.0
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class TASDEEQValidationError(Exception):
    """Raised when CSV data fails schema validation."""
    pass


class LoanStatus(str, Enum):
    """Valid loan statuses for TASDEEQ reporting."""
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFAULT = "default"
    RESTRUCTURED = "restructured"
    WRITTEN_OFF = "written_off"


@dataclass(slots=True)
class TASDEEQReportRow:
    """
    Represents a single row in the TASDEEQ CSV report.
    Validates all fields according to bureau schema.
    """
    report_date: date
    loan_id: str
    user_id: int
    cnic: str
    principal: Decimal
    outstanding: Decimal
    status: str
    installments_paid: int
    total_installments: int
    last_payment_date: str | None

    def __post_init__(self) -> None:
        """Validate all fields on instantiation."""
        self._validate_report_date()
        self._validate_loan_id()
        self._validate_user_id()
        self._validate_cnic()
        self._validate_principal()
        self._validate_outstanding()
        self._validate_status()
        self._validate_installments()
        self._validate_last_payment_date()

    def _validate_report_date(self) -> None:
        """Report date must be a valid date (typically today)."""
        if not isinstance(self.report_date, date):
            raise TASDEEQValidationError(f"Invalid report_date type: {type(self.report_date)}. Expected date.")

    def _validate_loan_id(self) -> None:
        """Loan ID must be non-empty string, alphanumeric with hyphens allowed."""
        if not self.loan_id or not isinstance(self.loan_id, str):
            raise TASDEEQValidationError(f"Invalid loan_id: '{self.loan_id}'. Must be non-empty string.")
        if len(self.loan_id) > 50:
            raise TASDEEQValidationError(f"Invalid loan_id: '{self.loan_id}'. Max length 50 chars.")
        if not all(c.isalnum() or c in '-_' for c in self.loan_id):
            raise TASDEEQValidationError(f"Invalid loan_id: '{self.loan_id}'. Only alphanumeric, hyphens, underscores allowed.")

    def _validate_user_id(self) -> None:
        """User ID must be positive integer."""
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise TASDEEQValidationError(f"Invalid user_id: {self.user_id}. Must be positive integer.")

    def _validate_cnic(self) -> None:
        """CNIC must be valid Pakistani CNIC format or 'N/A' if not available."""
        if self.cnic == "N/A":
            return
        # Pakistani CNIC format: 5 digits - 7 digits - 1 digit
        cnic_clean = self.cnic.replace("-", "").replace(" ", "")
        if not (len(cnic_clean) == 13 and cnic_clean.isdigit()):
            raise TASDEEQValidationError(f"Invalid cnic: '{self.cnic}'. Must be XXXXX-XXXXXXX-X format or 'N/A'.")

    def _validate_principal(self) -> None:
        """Principal must be non-negative decimal with max 2 decimal places."""
        if not isinstance(self.principal, Decimal):
            raise TASDEEQValidationError(f"Invalid principal type: {type(self.principal)}. Must be Decimal.")
        if self.principal < 0:
            raise TASDEEQValidationError(f"Invalid principal: {self.principal}. Must be non-negative.")
        if self.principal.as_tuple().exponent < -2:
            raise TASDEEQValidationError(f"Invalid principal: {self.principal}. Max 2 decimal places allowed.")

    def _validate_outstanding(self) -> None:
        """Outstanding must be non-negative decimal with max 2 decimal places, <= principal."""
        if not isinstance(self.outstanding, Decimal):
            raise TASDEEQValidationError(f"Invalid outstanding type: {type(self.outstanding)}. Must be Decimal.")
        if self.outstanding < 0:
            raise TASDEEQValidationError(f"Invalid outstanding: {self.outstanding}. Must be non-negative.")
        if self.outstanding.as_tuple().exponent < -2:
            raise TASDEEQValidationError(f"Invalid outstanding: {self.outstanding}. Max 2 decimal places allowed.")
        if self.outstanding > self.principal:
            raise TASDEEQValidationError(
                f"Invalid outstanding: {self.outstanding}. Cannot exceed principal {self.principal}."
            )

    def _validate_status(self) -> None:
        """Status must be one of the allowed TASDEEQ statuses."""
        valid_statuses = {status.value for status in LoanStatus}
        if self.status not in valid_statuses:
            raise TASDEEQValidationError(
                f"Invalid status: '{self.status}'. Must be one of: {', '.join(valid_statuses)}"
            )

    def _validate_installments(self) -> None:
        """Installments paid must be non-negative and <= total installments."""
        if not isinstance(self.installments_paid, int) or self.installments_paid < 0:
            raise TASDEEQValidationError(f"Invalid installments_paid: {self.installments_paid}. Must be non-negative integer.")
        if not isinstance(self.total_installments, int) or self.total_installments <= 0:
            raise TASDEEQValidationError(f"Invalid total_installments: {self.total_installments}. Must be positive integer.")
        if self.installments_paid > self.total_installments:
            raise TASDEEQValidationError(
                f"Invalid installments: {self.installments_paid} paid of {self.total_installments} total. "
                f"Paid cannot exceed total."
            )

    def _validate_last_payment_date(self) -> None:
        """Last payment date must be ISO format date string or 'N/A'."""
        if self.last_payment_date is None or self.last_payment_date == "N/A":
            return
        try:
            date.fromisoformat(self.last_payment_date)
        except (ValueError, TypeError):
            raise TASDEEQValidationError(
                f"Invalid last_payment_date: '{self.last_payment_date}'. "
                f"Must be ISO format (YYYY-MM-DD) or 'N/A'."
            )

    def to_csv_row(self) -> tuple:
        """Convert validated row to CSV tuple for output."""
        return (
            self.report_date.isoformat(),
            self.loan_id,
            self.user_id,
            self.cnic,
            str(self.principal),
            str(self.outstanding),
            self.status,
            self.installments_paid,
            self.total_installments,
            self.last_payment_date or "N/A",
        )


class TASDEEQCSVValidator:
    """Validates complete TASDEEQ CSV report structure and content."""

    REQUIRED_COLUMNS = [
        "Report Date",
        "Loan ID",
        "User ID",
        "CNIC",
        "Principal",
        "Outstanding",
        "Status",
        "Installments Paid",
        "Total Installments",
        "Last Payment Date",
    ]

    @classmethod
    def validate_report(cls, rows: list[TASDEEQReportRow]) -> dict[str, int]:
        """
        Validate a complete TASDEEQ report.

        Returns:
            Dictionary with validation statistics:
            - 'total_rows': Total rows processed
            - 'valid_rows': Successfully validated rows
            - 'errors': Number of rows with validation errors

        Raises:
            TASDEEQValidationError: If fatal validation issues found
        """
        if not rows:
            raise TASDEEQValidationError("Report must contain at least one data row.")

        valid_count = 0
        error_count = 0
        errors_list = []

        for idx, row in enumerate(rows, start=1):
            try:
                row  # Row validation happens in __post_init__
                valid_count += 1
            except TASDEEQValidationError as e:
                error_count += 1
                errors_list.append(f"Row {idx}: {str(e)}")

        # If more than 10% of rows have errors, consider it a failed report
        error_rate = error_count / len(rows)
        if error_rate > 0.10:
            error_summary = "\n".join(errors_list[:5])  # Show first 5 errors
            raise TASDEEQValidationError(
                f"Report validation failed: {error_count}/{len(rows)} rows ({error_rate*100:.1f}%) have errors.\n"
                f"First errors:\n{error_summary}"
            )

        return {
            "total_rows": len(rows),
            "valid_rows": valid_count,
            "errors": error_count,
        }

    @classmethod
    def get_csv_header(cls) -> tuple:
        """Get the required CSV header tuple."""
        return tuple(cls.REQUIRED_COLUMNS)
