"""
Real, cross-service test of the billing-sweep -> late-fee -> charity
disbursement pipeline -- a financial workflow test_order_lifecycle.py's
single happy-path run never reaches (it stops at down payment / VCN
issuance). Runs against the same live docker-compose stack; the billing
sweep and charity disbursement workers are invoked exactly as a real cron
job would (`docker compose run --rm ledger-service python -m
src.workers.<worker>`), not called in-process or mocked.

This is also the one Shariah-compliance invariant that must survive any
frontend rebuild: a late fee is a `charity_payable` liability, never
platform revenue (see accounting_service.py::record_late_fee, ledger audit
doc section "Business Rules a Frontend Must Respect").
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from tests.e2e._helpers import (
    LEDGER_HEADERS_FINANCE,
    WIDGET_URL,
    db_fetchrow,
    full_order_to_down_payment,
    poll_until,
    run_ledger_worker,
)

pytestmark = pytest.mark.asyncio

# apps/ledger-service/src/accounting/accounts.py::ACCOUNT_CODES -- journal
# entry lines carry the numeric GL code, not the human-readable key.
_CHARITY_PAYABLE_CODE = "2100"
_LATE_FEE_COLLECTIONS_CODE = "4003"


async def test_billing_sweep_applies_late_fee_to_charity_not_revenue(base_urls: dict[str, str]) -> None:
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["payment-orchestrator"], timeout=180.0) as pay, \
            httpx.AsyncClient(base_url=base_urls["ledger-service"], timeout=180.0) as ledger:

        flow = await full_order_to_down_payment(gw, pay, product_url=WIDGET_URL, installment_count=3)
        user_id = flow["user_id"]

        # Wait for Ledger Service's loan.created listener to have actually
        # materialized the installment schedule (Murabaha signing publishes
        # the event asynchronously -- see contract_signer.py).
        installment = await poll_until(
            lambda: db_fetchrow(
                "SELECT id, due_date, status FROM installments "
                "WHERE user_id = $1 AND is_down_payment = false "
                "ORDER BY installment_number ASC LIMIT 1",
                user_id,
            ),
            lambda r: r is not None,
            timeout=180.0,
            desc="first non-down-payment installment row to exist for the new loan",
        )
        installment_id = installment["id"]
        assert installment["status"] == "pending", installment

        # Far enough past any real due date (installment_count=3 schedules
        # span, at most, a handful of months) that the sweep is guaranteed
        # to treat it as overdue, without needing to backdate any row.
        as_of = (date.today() + timedelta(days=400)).isoformat()
        print(f"[billing_sweep] installment_id={installment_id} due_date={installment['due_date']!r} as_of={as_of}")

        result = run_ledger_worker("src.workers.billing_sweep_worker", "--as-of", as_of)
        print(f"[billing_sweep] worker stdout:\n{result.stdout}\n[billing_sweep] worker stderr:\n{result.stderr}")
        assert result.returncode == 0, f"billing_sweep_worker failed:\n{result.stdout}\n{result.stderr}"

        # NOTE: `installments.status`/`late_fee_amount` are NOT the signal to
        # poll here -- per LateFeeService.apply_late_fee_to_installment's own
        # docstring (BV-01/BV-04/BV-05), Ledger Service deliberately never
        # writes back to the shared `installments` table; it only publishes
        # events. Idempotency instead lives on the LateFeeCharityAllocation
        # row (UniqueConstraint on installment_id) and the late-fee
        # JournalEntry (source_type/source_id) -- both checked below. Live-
        # verified: after a real sweep run, `installments.status` stays
        # "pending" and `late_fee_amount` stays 0 forever, even though the
        # allocation + journal entry are correctly created.
        allocation = await poll_until(
            lambda: db_fetchrow(
                "SELECT id, late_fee_amount FROM late_fee_charity_allocations WHERE installment_id = $1",
                installment_id,
            ),
            lambda r: r is not None,
            timeout=20.0,
            desc="LateFeeCharityAllocation row to exist for the newly-applied late fee",
        )
        assert allocation["late_fee_amount"] and Decimal(str(allocation["late_fee_amount"])) > 0, allocation

        resp = await ledger.get(
            "/entries/",
            params={"source_type": "installment.late_fee", "limit": 100},
            headers=LEDGER_HEADERS_FINANCE,
        )
        assert resp.status_code == 200, resp.text
        entries = resp.json()["items"]
        matching = [e for e in entries if e["source_id"] == installment_id]
        assert matching, f"No late-fee journal entry found for installment {installment_id} among {entries}"
        late_fee_entry = matching[0]

        assert late_fee_entry["is_balanced"] is True, late_fee_entry
        account_codes_credited = {
            line["account_code"] for line in late_fee_entry["lines"] if line["credit_amount"] > 0
        }
        assert _CHARITY_PAYABLE_CODE in account_codes_credited, (
            f"Late fee must credit charity_payable ({_CHARITY_PAYABLE_CODE}), not revenue: {late_fee_entry}"
        )
        assert _LATE_FEE_COLLECTIONS_CODE not in account_codes_credited, (
            f"Late fee must NEVER credit late_fee_collections ({_LATE_FEE_COLLECTIONS_CODE}) as revenue: {late_fee_entry}"
        )


async def test_charity_disbursement_worker_pays_out_allocated_late_fees(base_urls: dict[str, str]) -> None:
    async with httpx.AsyncClient(base_url=base_urls["gateway"], timeout=180.0) as gw, \
            httpx.AsyncClient(base_url=base_urls["payment-orchestrator"], timeout=180.0) as pay, \
            httpx.AsyncClient(base_url=base_urls["ledger-service"], timeout=180.0) as ledger:

        flow = await full_order_to_down_payment(gw, pay, product_url=WIDGET_URL, installment_count=3)
        user_id = flow["user_id"]

        installment = await poll_until(
            lambda: db_fetchrow(
                "SELECT id FROM installments WHERE user_id = $1 AND is_down_payment = false "
                "ORDER BY installment_number ASC LIMIT 1",
                user_id,
            ),
            lambda r: r is not None,
            timeout=180.0,
            desc="first non-down-payment installment row to exist for the new loan",
        )
        installment_id = installment["id"]

        as_of = (date.today() + timedelta(days=400)).isoformat()
        result = run_ledger_worker("src.workers.billing_sweep_worker", "--as-of", as_of)
        assert result.returncode == 0, f"billing_sweep_worker failed:\n{result.stdout}\n{result.stderr}"

        allocation = await poll_until(
            lambda: db_fetchrow(
                "SELECT id, disbursed_at FROM late_fee_charity_allocations WHERE installment_id = $1",
                installment_id,
            ),
            lambda r: r is not None,
            timeout=20.0,
            desc="LateFeeCharityAllocation row to exist for the newly-applied late fee",
        )
        assert allocation["disbursed_at"] is None, "should not be pre-disbursed before the worker runs"

        # Override the two Shariah gates (nisab threshold, minimum-age) for
        # THIS one-off invocation only -- a single E2E test's late fee will
        # never naturally clear the real PKR 175,000 nisab or the real 7-day
        # minimum age, and this suite has no way to wait 7 real days. The
        # long-running ledger-service container's real config is untouched.
        result = run_ledger_worker(
            "src.workers.charity_disbursement_worker",
            "--payment-reference", "e2e-test-disbursement",
            extra_env={"CHARITY_DISBURSEMENT_MIN_AGE_DAYS": "0", "SHARIAH_NISAB_PKR": "1"},
        )
        assert result.returncode == 0, f"charity_disbursement_worker failed:\n{result.stdout}\n{result.stderr}"

        disbursed = await poll_until(
            lambda: db_fetchrow(
                "SELECT id, disbursed_at FROM late_fee_charity_allocations WHERE id = $1",
                allocation["id"],
            ),
            lambda r: r is not None and r["disbursed_at"] is not None,
            timeout=20.0,
            desc="allocation to be marked disbursed",
        )
        assert disbursed["disbursed_at"] is not None, disbursed

        resp = await ledger.get(
            "/entries/",
            params={"source_type": "charity.disbursement", "limit": 100},
            headers=LEDGER_HEADERS_FINANCE,
        )
        assert resp.status_code == 200, resp.text
        entries = resp.json()["items"]
        assert entries, "Expected at least one charity.disbursement journal entry after the worker ran"
        disbursement_entry = entries[0]
        assert disbursement_entry["is_balanced"] is True, disbursement_entry
        debit_accounts = {line["account_code"] for line in disbursement_entry["lines"] if line["debit_amount"] > 0}
        assert _CHARITY_PAYABLE_CODE in debit_accounts, (
            f"Disbursement must debit charity_payable ({_CHARITY_PAYABLE_CODE}), paying down the liability: {disbursement_entry}"
        )
