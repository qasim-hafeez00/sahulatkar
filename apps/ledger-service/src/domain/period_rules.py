from __future__ import annotations

from datetime import date
from enum import Enum


class PeriodStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


def assert_period_open(status: str) -> None:
    """Assert that a period is open for posting."""
    if status != PeriodStatus.OPEN:
        raise ValueError("PERIOD_CLOSED: Cannot post to a closed accounting period")


def is_date_in_period(target_date: date, start_date: date, end_date: date) -> bool:
    """Check if a date falls within the given period bounds."""
    return start_date <= target_date <= end_date
