# Rollback Process

**Status:** STABLE (application-level) — schema-level rollback is the confirmed gap.

## Application rollback

Standard container-image rollback: `kubectl rollout undo`, or re-running the CD pipeline against a prior commit SHA's already-built image. Not blocked by any known gap — this path works as long as no irreversible schema change shipped alongside the code being rolled back.

## Schema rollback — the confirmed gap

**Most Alembic migrations lack a working `downgrade()`** (`DB-GAP-01`) — meaning a bad schema change cannot currently be mechanically reversed via `alembic downgrade`. In practice, this means: if a deploy that includes a schema change turns out to be broken, the safe rollback path is to roll back the *application code* to the prior version while leaving the *schema* at the new (compatible-or-not) state — which only works cleanly if the new migration was purely additive (new nullable column, new table) and the old code doesn't choke on the schema being "ahead" of it. A destructive or backward-incompatible migration (dropped column, renamed table, `NOT NULL` added without a default) currently has **no safe rollback path** if it ships broken.

## Recommended immediate mitigation (given closing `DB-GAP-01` fully will take time)

Until every migration has a working `downgrade()`, adopt a stricter migration-writing discipline: prefer additive-only migrations wherever possible (add-nullable-column instead of alter-existing-column, soft-deprecate instead of drop), so that even without a formal `downgrade()`, a code-only rollback remains safe. This doesn't fix the underlying gap but reduces the practical blast radius while it's being closed.

## Rollback decision authority

Not documented — who is authorized to trigger a production rollback, and does it require the same manual-approval-gate rigor as a forward deploy, or can it be executed faster in an incident? Recommend this be explicit, since incident response (see [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md)) benefits from a rollback path that's *faster* to execute than a normal deploy, not equally gated.

## Related documents

[`34-deployment-process.md`](34-deployment-process.md), [`../07-database/134-migration-standards.md`](../07-database/134-migration-standards.md), [`../12-operations/41-incident-response-plan.md`](../12-operations/41-incident-response-plan.md).
