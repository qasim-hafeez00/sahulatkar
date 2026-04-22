from __future__ import annotations

import calendar
import re
from datetime import date


def get_period_bounds(period: str) -> tuple[date, date]:
    """
    Calculate the start and end dates for a given period string.
    
    Supported formats:
    - Monthly: "YYYY-MM" (e.g., "2026-04")
    - Quarterly: "YYYY-QN" (e.g., "2026-Q2")
    - Annual: "YYYY" (e.g., "2026")
    
    Returns:
        tuple[date, date]: (start_date, end_date)
        
    Raises:
        ValueError: If the period format is invalid.
    """
    quarter_match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if quarter_match:
        year = int(quarter_match.group(1))
        quarter = int(quarter_match.group(2))
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        start_date = date(year, start_month, 1)
        end_day = calendar.monthrange(year, end_month)[1]
        end_date = date(year, end_month, end_day)
        return start_date, end_date

    month_match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", period)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        start_date = date(year, month, 1)
        end_day = calendar.monthrange(year, month)[1]
        return start_date, date(year, month, end_day)

    year_match = re.fullmatch(r"\d{4}", period)
    if year_match:
        year = int(period)
        return date(year, 1, 1), date(year, 12, 31)

    raise ValueError("INVALID_PERIOD_FORMAT")


def get_period_key(target_date: date, period_type: str = "monthly") -> str:
    """
    Generate a period key for a given date and type.
    
    Args:
        target_date: The date to generate a key for.
        period_type: "monthly" or "quarterly".
        
    Returns:
        str: The period key (e.g., "2026-04" or "2026-Q2").
    """
    if period_type == "monthly":
        return f"{target_date.year}-{target_date.month:02d}"
    elif period_type == "quarterly":
        quarter = (target_date.month - 1) // 3 + 1
        return f"{target_date.year}-Q{quarter}"
    else:
        return str(target_date.year)
