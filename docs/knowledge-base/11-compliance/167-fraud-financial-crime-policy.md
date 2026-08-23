# Fraud / Financial Crime Policy

> **STATUS: INTERNAL DRAFT.** No formal financial-crime policy document exists; this consolidates what's implied by existing mechanisms and names the policy gaps explicitly.

## What exists (mechanism, not policy)

The Credit Engine's fraud-detection layers ([`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md)) and the blacklist/investigation workflow ([`../18-credit-risk-policy/95-fraud-investigation-workflow.md`](../18-credit-risk-policy/95-fraud-investigation-workflow.md)) constitute real fraud-*detection* capability — but a financial-crime **policy** additionally needs to specify things the mechanism alone doesn't: what constitutes confirmed fraud for reporting purposes, escalation to law enforcement, coordination with FMU on suspicious activity, and record-keeping requirements for fraud cases distinct from the general audit trail.

## Policy gaps

- No defined threshold or process for when confirmed fraud should be reported externally (to FMU, to police, to TASDEEQ as a negative flag beyond just credit reporting).
- No documented retention requirement for fraud-investigation case files, distinct from the general 7-year NADRA-response retention.
- No documented relationship between a fraud confirmation and the AML/STR process ([`166-transaction-monitoring.md`](166-transaction-monitoring.md)) — a confirmed fraud case plausibly should trigger an STR review even if it wasn't independently flagged by transaction monitoring, but this cross-trigger isn't specified anywhere.

## Relationship to the broader AML gap

This document and [`166-transaction-monitoring.md`](166-transaction-monitoring.md) together represent the same underlying gap from two angles: the platform has strong *credit-risk* fraud tooling but comparatively little *financial-crime-compliance* policy layered on top of it. Recommend Compliance treat these as a single work item (a financial-crime program covering both fraud and AML) rather than two independent policy documents, given how much they'd otherwise duplicate.

## Related documents

[`166-transaction-monitoring.md`](166-transaction-monitoring.md), [`37-kyc-aml-policy.md`](37-kyc-aml-policy.md), [`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md).
