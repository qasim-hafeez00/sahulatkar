# Incident Response Plan

**Status:** PLANNED — no formal incident-response policy exists in current engineering documentation. This document proposes a starting structure grounded in the platform's actual known failure modes (from `docs/PRODUCTION_GAPS_REPORT.md`) rather than a generic template, and should be reviewed/ratified by Engineering leadership and Ops before being treated as active policy.

## Why this matters more than usual for SahulatKar right now

Per [`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md), there is currently **no alerting, log aggregation, or distributed tracing running** — meaning the platform today has no automated way to detect most incidents. Until that's built, incident response is disproportionately dependent on manual detection (customer complaints, someone noticing) and on knowing, in advance, exactly which specific things are already known to be fragile — which is what the severity matrix below is built around.

## Proposed severity matrix

| Severity | Definition | Example (grounded in known platform gaps) |
|---|---|---|
| SEV-1 | Customer money at risk or platform-wide outage | Duplicate payment processed (webhook dedup gap, `GW-BL-13`); ledger entries posted unbalanced (`LS-CRIT-02`); VCN credential exposure |
| SEV-2 | Significant functional failure, workaround exists | Order stuck indefinitely due to a missing callback (extraction timeout, `product-extracted` never arrives); scraping worker down platform-wide (`PS-BUG-01`, if it recurs post-fix) |
| SEV-3 | Degraded but not blocking | HITL queue backlog past SLA; a specific merchant's extraction failing while others work |
| SEV-4 | Minor, no customer impact | Dead code path, cosmetic admin dashboard bug |

## Financial incident response — the category most specific to this platform

Given the concentration of known financial-correctness gaps documented throughout this knowledge base, a dedicated financial-incident sub-process is warranted:

| Incident type | Detection today | Immediate response |
|---|---|---|
| Duplicate/double payment | **No automated detection** (webhook dedup gap) — likely surfaces via customer complaint or manual reconciliation | Manual refund of the duplicate (once `RefundOrchestrator` exists — currently manual gateway-side action required); ledger correction entry |
| Incorrect/unbalanced ledger entry | **No automated detection** (`LS-CRIT-02` — debit=credit not validated at write time) | Manual query against `journal_entries`/`journal_entry_lines` to find the imbalance; correcting entry; root-cause the write path that allowed it |
| Incorrect settlement / reconciliation mismatch | **Reconciliation itself runs against mock data today** (`PO-CRIT-02`) — real mismatches may not be caught until this is fixed | Once live: flag via `GET /admin/finance/reconciliation`; manual investigation of the specific `gateway_txn_id` |
| Payment gateway outage | Health checks exist per-service but no alerting is wired to notify anyone | Manual monitoring until alerting is built; fail over to the next payment method in priority order where the outage is method-specific |
| Wrong installment/Murabaha calculation | Covered by the never-`xfail` critical-path tests (`test_cost_price_disclosure`, etc.) in CI — but a production data bug distinct from a code regression would still need manual detection today | Manual query against `loans`/`installments`; customer notification; correction |

## Security incident response

See [`../08-security/27-security-architecture.md`](../08-security/27-security-architecture.md) for the threat model this should be built against. No formal security-incident playbook (containment, eradication, notification obligations) exists yet in current documentation — recommend building one before launch, given several open items (no secret rotation, no rate limit on the VCN-decrypt endpoint, admin TOTP has no brute-force lockout) represent live exposure if exploited.

## Data breach response

Not documented anywhere in current engineering docs. Given the platform holds CNIC, KYC images, and payment-card data, this is a genuine gap Legal/Compliance/Security should close explicitly — including notification obligations that may apply under PECA 2016 or SECP data-protection expectations (see [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md), itself flagged as needing legal confirmation).

## Postmortem template (proposed)

```
What happened?
Why? (root cause, not just proximate trigger)
Impact? (customers affected, money involved, duration)
Root cause?
Fix?
Preventive action?
Owner?
Deadline?
```

## Related documents

[`../10-devops/35-monitoring-logging.md`](../10-devops/35-monitoring-logging.md), [`../08-security/27-security-architecture.md`](../08-security/27-security-architecture.md), [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md), `docs/PRODUCTION_GAPS_REPORT.md`.
