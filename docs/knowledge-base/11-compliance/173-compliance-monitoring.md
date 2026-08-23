# Compliance Monitoring

> **STATUS: INTERNAL DRAFT.**

## What exists

The `compliance_officer` RBAC role (see [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md)) has access to the KYC manual-review queue and audit-trail viewing — a real, if narrow, ongoing compliance function. The Shariah audit endpoint (`GET /admin/finance/shariah-report`) provides a periodic compliance check, though a thin one per [`../04-shariah/84-shariah-audit-process.md`](../04-shariah/84-shariah-audit-process.md).

## What a compliance monitoring function typically needs, and current status

- **A defined monitoring calendar** — which checks run at what cadence (daily, weekly, quarterly), covering which obligations. Not documented anywhere as a consolidated calendar; individual cadences exist in isolation (KYC 24hr SLA, Shariah quarterly audit) without a single view tying them together.
- **Ongoing metrics/dashboards for compliance-relevant KPIs** — e.g., % of KYC decisions within SLA, complaint volume/themes (once [`170-complaints-grievance-procedure.md`](170-complaints-grievance-procedure.md) exists), charity-disbursement completion rate. Not currently in [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md) — recommend adding a compliance-specific KPI section there.
- **A defined escalation path when monitoring surfaces an issue** — mirrors the same gap noted in [`../04-shariah/85-shariah-non-compliance-handling.md`](../04-shariah/85-shariah-non-compliance-handling.md) for Shariah-specific non-compliance; a general compliance-monitoring function needs the same kind of defined response process for non-Shariah findings (e.g., an AML gap, a licensing lapse).

## The meta-observation this category surfaces

Across all 10 documents in this Compliance category, the consistent pattern is: **obligations are named, mechanisms are thin-to-absent, and the connective tissue (who monitors, who escalates, who reports to leadership) is almost entirely undocumented.** This document, being the last in the category, is the right place to name that pattern explicitly: closing this category's gaps needs a named compliance monitoring *function* (a person or team with clear ownership) more than it needs any single additional policy document — the policies can be written, but without an owner actively monitoring against them, they don't function as compliance.

## Related documents

Every other document in this folder; [`../04-shariah/84-shariah-audit-process.md`](../04-shariah/84-shariah-audit-process.md), [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md).
