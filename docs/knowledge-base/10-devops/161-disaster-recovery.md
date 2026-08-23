# Disaster Recovery

**Status:** PLANNED — explicit Phase 4 target ("Disaster recovery runbook setup and execution simulation") per `docs/MASTER_PLAN.md` §8, not yet built.

## Scope of a DR plan for this platform, specifically

Beyond generic infrastructure DR (region outage, database failure — see [`../07-database/135-database-backup-recovery.md`](../07-database/135-database-backup-recovery.md)), this platform has domain-specific DR considerations worth naming explicitly:

- **VCN state during an outage.** If Payment Orchestrator or its connection to Stripe Issuing is unavailable, active VCNs remain live on the issuer side regardless — a DR plan should specify whether/how to bulk-void active VCNs if a prolonged outage makes it impossible to safely manage their lifecycle otherwise.
- **In-flight checkout automation during an outage.** A Playwright session mid-purchase when the Product Service goes down leaves the browser session, the merchant-side cart state, and the VCN charge status all in an ambiguous place — recovery needs a defined reconciliation step (check the VCN issuer's transaction log to determine if the charge actually went through) rather than assuming either "it definitely happened" or "it definitely didn't."
- **Ledger consistency after a partial-service outage.** Given the already-fragile event chain (missing `loan.created`, unvalidated debit=credit), a DR event that causes services to restart out of sync with each other could compound existing gaps — a full-platform recovery runbook should include a ledger-reconciliation pass as an explicit step, not assume the ledger self-heals.

## Regional resiliency

Single-region deployment (`ap-south-1`, ADR-007 in [`../14-project-management/44-architecture-decision-records.md`](../14-project-management/44-architecture-decision-records.md)) means a regional AWS outage is a full-platform DR event, not a partial one — multi-region active-active is an explicit Phase 5 (future) item, not current capability.

## What a DR runbook needs, minimally

Defined RTO/RPO targets (currently undocumented, see [`../07-database/135-database-backup-recovery.md`](../07-database/135-database-backup-recovery.md)), a step-by-step recovery procedure per failure scenario, a communication plan (who tells customers/regulators what, and when), and — critically — an actually-executed practice drill, since an untested runbook is not a reliable one.

## Related documents

[`../07-database/135-database-backup-recovery.md`](../07-database/135-database-backup-recovery.md), [`162-backup-restore.md`](162-backup-restore.md), [`163-business-continuity.md`](163-business-continuity.md).
