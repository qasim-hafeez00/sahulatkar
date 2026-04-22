from __future__ import annotations

import argparse
import asyncio
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.core.database import SessionLocal
from src.services.reconciliation_service import ReconciliationService


logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import a reconciliation settlement snapshot")
    parser.add_argument("--file", type=Path, help="Path to a JSON file containing settlement fields")
    parser.add_argument("--gateway", help="Gateway name for the settlement snapshot")
    parser.add_argument("--settlement-date", help="Settlement date in YYYY-MM-DD format")
    parser.add_argument("--expected-amount", type=Decimal, help="Expected settlement amount")
    parser.add_argument("--actual-amount", type=Decimal, help="Actual settlement amount")
    parser.add_argument("--reference", help="Optional gateway reference")
    parser.add_argument("--notes", help="Optional reconciliation notes")
    return parser


def _load_payload_from_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Reconciliation file must contain a JSON object")
    return payload


async def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.file is not None:
        payload = _load_payload_from_file(args.file)
    else:
        payload = {
            "gateway": args.gateway,
            "settlement_date": args.settlement_date,
            "expected_amount": args.expected_amount,
            "actual_amount": args.actual_amount,
            "reference": args.reference,
            "notes": args.notes,
        }

    required_fields = ("gateway", "settlement_date", "expected_amount", "actual_amount")
    missing_fields = [field for field in required_fields if payload.get(field) in (None, "")]
    if missing_fields:
        raise ValueError(f"Missing required reconciliation fields: {', '.join(missing_fields)}")

    async with SessionLocal() as session:
        service = ReconciliationService(session)
        result = await service.import_snapshot(
            gateway=str(payload["gateway"]),
            settlement_date=str(payload["settlement_date"]),
            expected_amount=Decimal(str(payload["expected_amount"])),
            actual_amount=Decimal(str(payload["actual_amount"])),
            reference=payload.get("reference"),
            notes=payload.get("notes"),
        )
        logger.info("Reconciliation snapshot import completed", extra={"result": result})


if __name__ == "__main__":
    asyncio.run(main())