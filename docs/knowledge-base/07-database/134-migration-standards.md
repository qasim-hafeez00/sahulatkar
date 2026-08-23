# Migration Standards

**Status:** STABLE (the standard) — compliance gap is the central finding.

## The standard (per `docs/MASTER_PLAN.md`'s pre-push checklist)

- Every model change requires a new Alembic migration file.
- Every migration must be reversible — a working `downgrade()`, not just `upgrade()`.
- Migrations are run and verified in CI: `alembic upgrade head → downgrade -1 → upgrade head`, confirming reversibility on every push.

## Current compliance

**Most migrations lack a working `downgrade()` implementation** (`DB-GAP-01`) — despite the CI check above nominally existing, this suggests either the CI check isn't actually catching the gap (worth investigating directly — does it only check the *most recent* migration's reversibility, missing gaps in older ones?), or the gap was introduced before the check existed and hasn't been backfilled.

## Why this matters operationally, not just as a testing nicety

A production migration that turns out to be wrong (bad data transformation, unexpected lock contention, a bug in the new schema) needs a fast, reliable rollback path. Without working `downgrade()` implementations, a bad migration in production may require a manual, ad hoc fix under incident pressure rather than a tested, mechanical rollback — directly relevant to [`../10-devops/34-deployment-process.md`](../10-devops/34-deployment-process.md)'s rollback section.

## Additional standards observed in the schema itself

- `system_parameters` exists but has no seed migration populating defaults (`DB-GAP-04`) — a reminder that "the table exists" and "the migration is complete" are different claims; a migration standard should include a checklist item for whether new configuration tables need seed data, not just schema.
- Trigger definitions use raw DDL with no version tracking (`DB-GAP-03`) — recommend a documented pattern for how triggers should be migrated (always `CREATE OR REPLACE`, with the trigger's own change history traceable through migration file history).
- Partial/composite indexes critical to performance (e.g., `installments(due_date, user_id) WHERE status='pending'`) should be called out explicitly in migration PR descriptions given how load-bearing they are — not a formal rule yet, but a good practice to adopt given how much the billing sweep depends on that specific index.

## Related documents

[`25-database-architecture.md`](25-database-architecture.md), [`../10-devops/34-deployment-process.md`](../10-devops/34-deployment-process.md), [`132-database-schema-documentation.md`](132-database-schema-documentation.md).
