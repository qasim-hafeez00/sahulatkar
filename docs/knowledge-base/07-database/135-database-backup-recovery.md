# Database Backup & Recovery

**Status:** PLANNED — no explicit backup/recovery policy (backup frequency, retention, tested restore procedure) is documented anywhere in the reviewed engineering materials, despite RDS (which provides automated backup capability) being the stated production database. This is a genuine gap, not a "not applicable" item — flagged clearly rather than assumed.

## What's implied by the infrastructure choice, but not confirmed as configured

AWS RDS for PostgreSQL provides automated daily snapshots and point-in-time recovery by default when enabled — but current Terraform module documentation (`infra/terraform/modules/rds/`) is referenced only at the module-existence level in engineering docs, without confirming backup retention period, snapshot frequency, or whether point-in-time recovery is actually enabled for the production RDS instance.

## What's missing entirely

- **A documented Recovery Point Objective (RPO)** — how much data loss is acceptable in a worst-case scenario (measured in minutes/hours since last backup).
- **A documented Recovery Time Objective (RTO)** — how long a restore is expected/allowed to take.
- **A tested restore procedure** — has anyone actually practiced restoring from a backup, end to end, including bringing the 6 dependent services back online against the restored database? Not referenced anywhere.
- **Backup encryption confirmation** — given the database holds encrypted PII (CNIC, VCN details via `pgcrypto`), backups should inherit that protection; not confirmed.
- **Cross-region backup replication** — relevant given the single-region deployment (ADR-007 in [`../14-project-management/44-architecture-decision-records.md`](../14-project-management/44-architecture-decision-records.md)) means a regional AWS outage could threaten both the live database and its backups if they're not replicated elsewhere (while still respecting the PECA 2016 data-residency commitment to Pakistan-adjacent infrastructure).

## Relationship to disaster recovery generally

This document is the database-specific slice of the broader gap noted in [`../10-devops/`](../10-devops/) — "disaster recovery runbook setup and execution simulation" is listed as an explicit Phase 4 target in `docs/MASTER_PLAN.md` §8 but, per the audit, Phase 4 work has not substantially begun. Database backup/recovery specifically should be one of the first pieces of that Phase 4 work completed, given it's the single hardest thing to reconstruct after the fact if genuinely lost.

## Related documents

[`25-database-architecture.md`](25-database-architecture.md), [`../10-devops/33-infrastructure-architecture.md`](../10-devops/33-infrastructure-architecture.md), [`../14-project-management/43-product-roadmap.md`](../14-project-management/43-product-roadmap.md).
