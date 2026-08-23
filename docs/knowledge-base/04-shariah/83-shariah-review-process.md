# Shariah Review Process

> **STATUS: INTERNAL DRAFT — proposed process, not yet ratified.** No formal review process is documented anywhere in current engineering materials; this is a starting proposal for Leadership/the Shariah board to adopt, amend, or replace.

## Proposed process for a new or changed product feature

```
1. Product/Engineering identifies a change that touches financing structure,
   pricing, contracts, or transaction flow
2. A submission is prepared for the Shariah board:
   - What is changing and why
   - The specific Shariah-relevant question(s) at stake
   - Any relevant precedent (prior board rulings, cited standards)
3. Board reviews and rules — recorded in the Shariah Decision Register
   (see 19-shariah-review-register.md)
4. If approved: implementation proceeds, contract template version bumped
   if applicable, re-certification triggered
5. If rejected or conditional: Product/Engineering revises and resubmits
6. Nothing ships to production until step 3 concludes with approval
```

## Why step 6 is the load-bearing rule

The confirmed process failure already on record — the tiered Murabaha markup shipping in code with an open `TODO` for board sign-off rather than waiting for it — is exactly what step 6 exists to prevent. **Recommend this be treated as a release gate, not a best-effort guideline**, enforced the same way the hard-gate CI test is enforced for VCN issuance (i.e., a checklist item that blocks a release, not a suggestion an engineer can deprioritize under time pressure).

## Trigger conditions requiring review (proposed)

- Any change to markup/profit rates, fee structures, or how they're calculated.
- Any change to the Wakalah or Murabaha contract template text.
- Any new financing product or plan type.
- Any change to the late-fee/charity-routing mechanism.
- Any change to the prohibited-categories list's scope or basis.

## SLA (not yet defined — for the board to set)

No turnaround-time commitment is documented. Recommend the board and Leadership agree an SLA (e.g., 2 weeks for standard reviews, expedited path for urgent items) so this process doesn't become a bottleneck that pressures engineering back toward the ship-first pattern that already happened once.

## Related documents

[`82-shariah-advisor-board.md`](82-shariah-advisor-board.md), [`19-shariah-review-register.md`](19-shariah-review-register.md), [`86-product-change-shariah-review.md`](86-product-change-shariah-review.md).
