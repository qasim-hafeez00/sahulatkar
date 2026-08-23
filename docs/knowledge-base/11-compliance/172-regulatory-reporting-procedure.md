# Regulatory Reporting Procedure

> **STATUS: INTERNAL DRAFT.**

## Reporting obligations referenced in engineering docs

| Report | Regulator | Cadence | Current implementation status |
|---|---|---|---|
| RCD-1 | SBP | Monthly | **Not referenced anywhere as an implemented process** — no report-generation logic, no submission mechanism |
| Suspicious Transaction Report (STR) | FMU | Within 7 days of detection | **No transaction-monitoring capability to detect what would trigger one** — see [`166-transaction-monitoring.md`](166-transaction-monitoring.md) |
| Currency Transaction Report (CTR) | FMU | Automatic, threshold-based | **No detection logic implemented** |
| TASDEEQ credit bureau reporting | TASDEEQ | Per-transaction (positive on payment, negative on default) | Referenced in the collections timeline as a design intent; live-integration status not confirmed |
| Shariah compliance report | Internal (Shariah Board), possibly SECP-facing | Quarterly (per governance cadence) | `GET /admin/finance/shariah-report` exists but the underlying audit logic is thin (`GW-BL-14`), see [`../04-shariah/84-shariah-audit-process.md`](../04-shariah/84-shariah-audit-process.md) |

## The gap pattern across this table

Every row above shares the same shape: a reporting *obligation* is named in engineering documentation, but the *mechanism* to actually generate and submit that report doesn't exist. This is consistent with the broader pattern in this compliance category — obligations are known and cited, but implementation lags meaningfully behind.

## Recommended prioritization

Given RCD-1 (monthly, SBP) and STR/CTR (FMU) both currently have zero implementation and represent the most direct regulatory exposure if SahulatKar is in fact operating under a license that requires them, **these should be Compliance/Engineering's top priority in this entire category** — ahead of, e.g., the Shariah reporting improvements, which at least has a working (if thin) mechanism already.

## Related documents

[`164-licensing-regulatory-assessment.md`](164-licensing-regulatory-assessment.md), [`166-transaction-monitoring.md`](166-transaction-monitoring.md), [`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md).
