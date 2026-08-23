# Ledger Invariants

**Status:** STABLE (as design intent) — this document exists specifically to state the rules that *should* always hold, several of which currently don't, so they can be tracked as a checklist rather than scattered across other documents.

## The invariants

| Invariant | Currently enforced? |
|---|---|
| Debits = credits, on every journal entry | **No** — `LS-CRIT-02` |
| Every financial transaction is immutable once posted (no direct edits to a posted entry — corrections go through a reversal, not a mutation) | Presumed by design (no `UPDATE` path documented for posted entries) but not independently confirmed against actual code |
| No direct balance modification (balances are always *derived* from posted entries, never written directly) | Presumed by design (`balance_service.py` computes from entries) — **known gap:** if the balance-snapshot worker fails, there is no confirmed fallback to recalculate on-the-fly, so a stale snapshot could effectively become a "direct" (stale) balance in practice (`LS-BL-03`) |
| Every signed Murabaha contract eventually has corresponding journal entries | **No** — currently true for zero loans, due to the missing `loan.created` event |
| Late fees collected always equal late fees disbursed to charity | **No** — disbursement is a stub (`LS-CRIT-03`) |
| A closed accounting period cannot receive new entries dated within it | **No** — period close does not currently prevent backdated entries (`LS-BL-02`) |
| Account codes referenced in a manual entry must exist in the chart of accounts | **No** — invalid codes currently cause a raw DB foreign-key violation (500 error) rather than being validated and rejected cleanly (`LS-BL-01`) |

## Why this list matters more than a typical "nice to have" invariant checklist

For most software, an unenforced invariant is a bug. For a ledger, an unenforced invariant means **the numbers cannot be trusted** — every financial report, every Shariah compliance report, every reconciliation depends on these holding. This table should be the first thing engineering checks off before SahulatKar handles real customer money at scale, not a background-priority cleanup item.

## Recommended test coverage

Every row above maps directly to a test case in [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md) — that document's "core invariants to test explicitly" table is this same list, written from the QA angle.

## Related documents

[`111-double-entry-accounting-model.md`](111-double-entry-accounting-model.md), [`../09-qa/32-financial-transaction-test-strategy.md`](../09-qa/32-financial-transaction-test-strategy.md), [`115-reconciliation-process.md`](115-reconciliation-process.md).
