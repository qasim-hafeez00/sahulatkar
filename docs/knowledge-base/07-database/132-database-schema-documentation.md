# Database Schema Documentation

**Status:** STABLE as a **pointer document** — the platform's full schema (169 tables across 13 domains per the design spec) is not reproduced table-by-table in this knowledge base; [`26-database-dictionary.md`](26-database-dictionary.md) covers the core ~30 tables referenced across the module specs. This document names the gap and points to where the rest lives.

## Where the full schema actually lives

1. **Alembic migrations** (`db/migrations/versions/`) — the single source of truth for the live schema at any point in time; 49 migrations present as of the last audit.
2. **Original DB design research** — `docs/Sahulatkar-docs/SahulatKar_DB_Design_Volume1.txt` and `Volume2.txt` (converted from the original `.docx` research documents), which predate and informed the current schema.
3. **Per-module specs** (`docs/System-md-files/M01`–`M12`) — each module's "Database Tables" section documents that module's owned tables, which is where [`26-database-dictionary.md`](26-database-dictionary.md) sourced its entries from.

## Why this knowledge base doesn't reproduce all 169 tables

Reproducing every table here would create a second source of truth that drifts from the actual migrations the moment either one changes — a well-known documentation anti-pattern. [`26-database-dictionary.md`](26-database-dictionary.md) deliberately covers only the ~30 tables that are referenced by name across the workflow/architecture documents in this knowledge base (i.e., the tables a reader is likely to need context for while reading elsewhere), and explicitly defers to the migrations for the complete, authoritative list.

## Recommended follow-up

If a complete, standalone schema reference is needed (e.g., for onboarding a new database engineer, or for a formal data-governance exercise), it should be **generated from the live migrations** (e.g., via a schema-introspection tool run against a migrated database) rather than hand-maintained — hand-maintaining 169 tables' worth of documentation would go stale within weeks of the first schema change.

## Related documents

[`26-database-dictionary.md`](26-database-dictionary.md), [`131-er-diagram.md`](131-er-diagram.md), [`134-migration-standards.md`](134-migration-standards.md).
