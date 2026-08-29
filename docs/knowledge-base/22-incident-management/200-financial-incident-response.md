# Financial Incident Response

**Status:** STABLE (proposed) — standalone version of the financial-incident table already in [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), pulled out here since financial incidents are this platform's single most concentrated risk category (per the sheer number of ledger/payment gaps documented throughout this knowledge base) and deserve a dedicated, quickly-referenceable playbook rather than being one section among several in a general incident plan.

## Financial incident types and response

| Incident type | Detection today | Immediate response |
|---|---|---|
| Duplicate/double payment | No automated detection (webhook dedup gap) | Manual refund of the duplicate via gateway portal (see [`../12-operations/176-refund-sop.md`](../12-operations/176-refund-sop.md)); ledger correction entry |
| Unbalanced/incorrect ledger entry | No automated detection (`LS-CRIT-02`) | Manual query against `journal_entries`/`journal_entry_lines`; correcting entry; root-cause the write path |
| Reconciliation mismatch | Reconciliation runs on mock data today (`PO-CRIT-02`), so live mismatches may go undetected until this is fixed | Once live: investigate the specific `gateway_txn_id` flagged |
| Gateway outage | No alerting (see [`../10-devops/160-alerting.md`](../10-devops/160-alerting.md)) | Manual monitoring; fail over to the next payment method in priority order if the outage is method-specific |
| Wrong Murabaha/installment calculation | Covered by never-`xfail` CI tests for code regressions; a production *data* bug (as opposed to a code regression) still needs manual detection | Manual query against `loans`/`installments`; customer notification; correction |
| Charity disbursement failure/discrepancy | Disbursement is currently a stub (`LS-CRIT-03`) — this is a standing, known condition, not really an "incident" to detect, but should be tracked toward resolution with the same urgency as a real incident given its Shariah-compliance dimension | Prioritize fixing `LS-CRIT-03` directly; in the interim, track accrued-but-undisbursed charity as a known liability |

## Escalation

Any financial incident above SEV-2 (see [`199-incident-severity-matrix.md`](199-incident-severity-matrix.md)) should involve Finance directly in the response, not just Engineering — a financially-correct-looking fix (the code runs without error) is not the same as a financially-*correct* fix, and Finance's sign-off should be part of closing any financial incident, not just Engineering's.

## Related documents

[`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md), [`../20-ledger-accounting/113-ledger-invariants.md`](../20-ledger-accounting/113-ledger-invariants.md), [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md).
