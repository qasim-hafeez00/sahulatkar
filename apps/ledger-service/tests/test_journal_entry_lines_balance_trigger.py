from __future__ import annotations

"""
Regression test for migration 085
(db/migrations/versions/085_journal_entry_lines_balance_trigger.py): a
Postgres constraint trigger (`trg_journal_entry_lines_balance_check`,
DEFERRABLE INITIALLY DEFERRED) that rejects a transaction at COMMIT time if
SUM(debit_amount)/SUM(credit_amount) on journal_entry_lines (grouped by
journal_id) doesn't match the owning journal_entries row's
total_debit/total_credit.

This is a real PL/pgSQL trigger -- it cannot be exercised against the
suite's default SQLite in-memory backend (see tests/conftest.py:
`TEST_DATABASE_URL = os.getenv("LEDGER_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")`).
There is no pre-existing `pytest.mark.postgres`-style skip marker anywhere in
this repo (grepped for `skipif`/`requires_postgres`/etc. -- none exist), so
this module builds directly on the one Postgres opt-in mechanism conftest.py
already defines: `LEDGER_TEST_DATABASE_URL`. It also falls back to
`DATABASE_URL` (what CI's `python-test` job exports for a real Postgres
service container -- see .github/workflows/ci.yml) and finally to this
service's own documented local-dev default (`src/config.py`'s
`Settings.database_url`), so the test runs for real:
  - on a dev machine with the local Postgres this repo already assumes
    (sk_app/localdev123@localhost:5432/sahulatkar -- confirmed reachable and
    matching `.env`'s PG_PASSWORD in this environment), and
  - opportunistically in CI, if the postgres service container is reachable.
None of this touches the global `engine`/`db_session` fixtures other tests
use, so the rest of the (SQLite-backed) suite is unaffected either way -- if
no Postgres is reachable at all, this module's tests just skip.

Rather than re-declaring the trigger's DDL by hand (risking drift from the
real migration), each test applies the actual migration module's `upgrade()`
function, loaded from db/migrations/versions/085_*.py by file path and run
through a real `alembic.operations.Operations` context bound to the test
connection -- exactly the DDL that will run in production.

Each test creates its own throwaway Postgres schema (search_path-scoped) with
just the two tables the trigger cares about, and drops it afterward, so this
never touches the shared dev database's real `public` schema data.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_PATH = _REPO_ROOT / "db" / "migrations" / "versions" / "085_journal_entry_lines_balance_trigger.py"

# Candidate Postgres URLs, in priority order. The first two are opt-in env
# vars (LEDGER_TEST_DATABASE_URL mirrors conftest.py's own convention;
# DATABASE_URL is what CI's postgres-backed test job exports). The third is
# this service's committed local-dev default (src/config.py), which is what
# makes this test actually run (not just skip) on a normal dev checkout.
_CANDIDATE_ENV_VARS = ("LEDGER_TEST_DATABASE_URL", "DATABASE_URL")
_LOCAL_DEV_FALLBACK_URL = "postgresql+asyncpg://sk_app:localdev123@localhost:5432/sahulatkar"


def _candidate_urls() -> list[str]:
    import os

    urls = []
    for var in _CANDIDATE_ENV_VARS:
        val = os.getenv(var)
        if val and "postgresql" in val:
            urls.append(val)
    urls.append(_LOCAL_DEV_FALLBACK_URL)
    return urls


def _load_migration_085():
    spec = importlib.util.spec_from_file_location(
        "migration_085_journal_entry_lines_balance_trigger", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_migration_085_upgrade(sync_conn) -> None:
    """Runs the real migration's upgrade() DDL against `sync_conn`, bound
    through a genuine Alembic Operations context (so `op.execute(...)` inside
    the migration module resolves correctly) -- called via
    AsyncConnection.run_sync, the same technique db/migrations/env.py uses to
    bridge async SQLAlchemy connections into Alembic's sync API."""
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    migration = _load_migration_085()
    ctx = MigrationContext.configure(sync_conn)
    with Operations.context(ctx):
        migration.upgrade()


@pytest.fixture
async def pg_journal_schema():
    """Yields (engine, schema_name) for a throwaway Postgres schema
    containing minimal journal_entries/journal_entry_lines tables plus the
    real migration-085 trigger, or skips the test if no Postgres instance
    is reachable at all."""
    engine = None
    for url in _candidate_urls():
        candidate_engine = create_async_engine(url)
        try:
            async with candidate_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            engine = candidate_engine
            break
        except Exception:
            await candidate_engine.dispose()

    if engine is None:
        pytest.skip(
            "No reachable Postgres instance for the migration-085 trigger test "
            "(this trigger is real PL/pgSQL and cannot run against the suite's "
            "default SQLite backend). Set LEDGER_TEST_DATABASE_URL or "
            "DATABASE_URL to a reachable postgresql+asyncpg:// URL to run it."
        )

    schema = f"trig085_{uuid.uuid4().hex[:10]}"
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        await conn.execute(
            text(
                """
                CREATE TABLE journal_entries (
                    id BIGSERIAL PRIMARY KEY,
                    total_debit NUMERIC(14, 2) NOT NULL,
                    total_credit NUMERIC(14, 2) NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE journal_entry_lines (
                    id BIGSERIAL PRIMARY KEY,
                    journal_id BIGINT NOT NULL REFERENCES journal_entries(id),
                    account_id BIGINT NOT NULL,
                    debit_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
                    credit_amount NUMERIC(14, 2) NOT NULL DEFAULT 0
                )
                """
            )
        )
        await conn.run_sync(_apply_migration_085_upgrade)

    try:
        yield engine, schema
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def test_balanced_journal_entry_lines_commit_succeeds(pg_journal_schema):
    """Sanity check: the trigger must NOT reject a genuinely balanced entry."""
    engine, schema = pg_journal_schema

    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        journal_id = (
            await conn.execute(
                text("INSERT INTO journal_entries (total_debit, total_credit) VALUES (100.00, 100.00) RETURNING id")
            )
        ).scalar_one()

    # Should commit without raising.
    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        await conn.execute(
            text(
                "INSERT INTO journal_entry_lines (journal_id, account_id, debit_amount, credit_amount) "
                f"VALUES ({journal_id}, 1, 100.00, 0)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO journal_entry_lines (journal_id, account_id, debit_amount, credit_amount) "
                f"VALUES ({journal_id}, 2, 0, 100.00)"
            )
        )

    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        count = (
            await conn.execute(text(f"SELECT COUNT(*) FROM journal_entry_lines WHERE journal_id = {journal_id}"))
        ).scalar_one()
    assert count == 2


async def test_unbalanced_journal_entry_lines_rejected_at_commit(pg_journal_schema):
    """Core regression: inserting journal_entry_lines that don't sum to the
    journal_entries header's total_debit/total_credit -- bypassing
    AccountingService entirely, via a raw insert -- must be rejected when the
    (deferred) transaction commits, and nothing must be persisted."""
    engine, schema = pg_journal_schema

    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        journal_id = (
            await conn.execute(
                text("INSERT INTO journal_entries (total_debit, total_credit) VALUES (50.00, 50.00) RETURNING id")
            )
        ).scalar_one()

    with pytest.raises(DBAPIError, match="JOURNAL_ENTRY_LINES_SUM_MISMATCH"):
        async with engine.begin() as conn:
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            # Debit 50 lands correctly, but credit only 40 -- unbalanced.
            await conn.execute(
                text(
                    "INSERT INTO journal_entry_lines (journal_id, account_id, debit_amount, credit_amount) "
                    f"VALUES ({journal_id}, 1, 50.00, 0)"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO journal_entry_lines (journal_id, account_id, debit_amount, credit_amount) "
                    f"VALUES ({journal_id}, 2, 0, 40.00)"
                )
            )

    # The whole transaction must have rolled back -- no orphaned lines.
    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        count = (
            await conn.execute(text(f"SELECT COUNT(*) FROM journal_entry_lines WHERE journal_id = {journal_id}"))
        ).scalar_one()
    assert count == 0


async def test_unbalanced_via_update_also_rejected_at_commit(pg_journal_schema):
    """The trigger fires on UPDATE as well as INSERT: a balanced entry whose
    line is later mutated (e.g. by a buggy fix-up script) to no longer match
    the header must also be rejected."""
    engine, schema = pg_journal_schema

    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        journal_id = (
            await conn.execute(
                text("INSERT INTO journal_entries (total_debit, total_credit) VALUES (75.00, 75.00) RETURNING id")
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO journal_entry_lines (journal_id, account_id, debit_amount, credit_amount) "
                f"VALUES ({journal_id}, 1, 75.00, 0)"
            )
        )
        line_id = (
            await conn.execute(
                text(
                    "INSERT INTO journal_entry_lines (journal_id, account_id, debit_amount, credit_amount) "
                    f"VALUES ({journal_id}, 2, 0, 75.00) RETURNING id"
                )
            )
        ).scalar_one()

    with pytest.raises(DBAPIError, match="JOURNAL_ENTRY_LINES_SUM_MISMATCH"):
        async with engine.begin() as conn:
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            await conn.execute(text(f"UPDATE journal_entry_lines SET credit_amount = 60.00 WHERE id = {line_id}"))

    async with engine.begin() as conn:
        await conn.execute(text(f'SET search_path TO "{schema}"'))
        credit_amount = (
            await conn.execute(text(f"SELECT credit_amount FROM journal_entry_lines WHERE id = {line_id}"))
        ).scalar_one()
    # Rolled back -- the bad update never stuck.
    assert str(credit_amount) == "75.00"
