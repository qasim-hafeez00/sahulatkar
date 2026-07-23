# Cross-cutting Backlog

Items that are known, real, and not yet scheduled into a phase of
[`plan.md`](plan.md) / [`MASTER_PLAN.md`](MASTER_PLAN.md). Move an item into a
phase (and delete it here) once it's actually scheduled.

## Frontend dependency drift (web-admin)

- **lucide-react**: pinned to the 0.x line; upstream is on the 1.x major.
- **Next.js 14 / React 18** on `web-admin`, vs. Next 16 / React 19 available upstream.

**Why not auto-scheduled:** this is a breaking, visually-verifiable bump across
~35 admin dashboard modules (icon API changes in lucide-react 1.x, React 19's
stricter behavior, Next 16 App Router changes). It needs a human to actually
click through the affected pages after the bump, not just a green CI run —
not something to fire-and-forget to an agent.

**Suggested approach when picked up:** one dedicated track, isolated on its
own branch, upgrading one major (lucide-react first, lowest blast radius) at
a time rather than all three at once, with a manual pass over the dashboard
after each step before moving to the next.

## Gateway pre-existing test failures (found during Phase 2, out of scope there)

9 failures on a full `pytest` run of `apps/gateway`, unrelated to the Phase 2
mutation-testing track (which only touched `rate_limit.py` / `config.py` /
`dependencies.py` / `main.py`). Root causes, at least 3 distinct:

- `admin_sessions` table used via raw SQL in `admin_auth.py` has no ORM
  model, so it's absent from the SQLite test schema
  (`Base.metadata.create_all()` only registers models it imports).
- A payment status transition mismatch in `test_payments_flow.py`.
- A CNIC `memoryview`/`str` type error in contract generation.
- An order-search `ilike` mismatch.

Not fixed yet because none of them are Phase 2 regressions — fixing them is
real, separate work in gateway's auth/payments/contracts code, not a
mutation-testing follow-up.
