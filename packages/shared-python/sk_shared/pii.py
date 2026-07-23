"""PII masking helpers for values that must never appear unmasked in logs, alert evidence, or
explanation payloads that admins/analysts view directly (fraud_alerts.evidence,
manual_review_queue.notes, risk_assessments.explanation, application logs).

Masking, not redaction: enough of the value survives for an analyst to recognize "yes, this
is the same CNIC/phone I'm looking at in the KYC record" without the full number being
readable or exportable from a log line or an admin-facing JSON response.
"""
from __future__ import annotations

import re
from typing import Any, Optional

_NON_DIGIT_RE = re.compile(r"\D")


def mask_cnic(value: Optional[str]) -> Optional[str]:
    """13-digit Pakistani CNIC (with or without dashes) -> first 2 + last 2 digits visible."""
    if not value:
        return value
    digits = _NON_DIGIT_RE.sub("", value)
    if len(digits) != 13:
        return "***"
    return f"{digits[:2]}{'*' * 9}{digits[-2:]}"


def mask_phone(value: Optional[str]) -> Optional[str]:
    """Phone number -> leading 2 + trailing 2 digits visible, rest masked."""
    if not value:
        return value
    digits = _NON_DIGIT_RE.sub("", value)
    if len(digits) < 4:
        return "*" * len(digits)
    return f"{digits[:2]}{'*' * (len(digits) - 4)}{digits[-2:]}"


_PII_KEY_MASKERS = {
    "cnic": mask_cnic,
    "cnic_number": mask_cnic,
    "phone": mask_phone,
    "phone_number": mask_phone,
}


def mask_pii_dict(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Recursively mask any dict key that looks like a CNIC/phone field (case-insensitive),
    leaving every other key untouched. Meant for the boundary where evidence/notes payloads
    are built for admin-facing columns, so a future data source that starts including raw
    identifiers there doesn't silently leak them."""
    if not isinstance(payload, dict):
        return payload
    masked: dict[str, Any] = {}
    for key, value in payload.items():
        masker = _PII_KEY_MASKERS.get(key.lower()) if isinstance(key, str) else None
        if masker and isinstance(value, str):
            masked[key] = masker(value)
        elif isinstance(value, dict):
            masked[key] = mask_pii_dict(value)
        elif isinstance(value, list):
            masked[key] = [mask_pii_dict(item) if isinstance(item, dict) else item for item in value]
        else:
            masked[key] = value
    return masked
