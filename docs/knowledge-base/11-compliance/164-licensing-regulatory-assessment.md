# Licensing / Regulatory Assessment

> **STATUS: INTERNAL DRAFT.** Not legal advice, not a completed regulatory assessment. This document states plainly what is *not known* from this codebase, which is itself the most important finding.

## The central finding

**SahulatKar's actual current licensing/registration status with SECP (or any other Pakistani financial regulator) is not recorded anywhere in this repository.** No document, config file, or code comment states whether the company holds an NBFC license, is operating under a Regulatory Sandbox admission, or is operating without either. This is stated as plainly as possible because it's the single most consequential unknown in the entire compliance documentation set — every other compliance document in this knowledge base assumes *some* licensing basis exists or is being pursued, without being able to confirm which.

## What engineering documentation assumes, without confirming

`docs/System-md-files/00Sahulatkar-System.md`'s regulatory table lists "NBFC license / Regulatory Sandbox" under SECP as a requirement — phrased as a requirement to be met, not a confirmed status. `docs/MASTER_PLAN.md` §8 lists "SECP regulatory documentation" as a Phase 4 (not-yet-started) task.

## What this means practically

Every product decision that assumes a specific regulatory classification (e.g., whether the 4%/tiered markup is legally a "fee" or would be reclassified as interest-equivalent under some licensing category, whether the Wakalah/Murabaha structure requires specific Islamic-finance licensing distinct from conventional NBFC licensing) is currently being made **without confirmed knowledge of which regulatory regime actually applies**. This is a business-critical gap, not a documentation nicety.

## Recommended immediate action

Legal/Leadership should determine and record: (1) current licensing status, (2) which licensing category is being pursued if not yet obtained, (3) an explicit go/no-go readiness assessment against that category's requirements — and this document should be updated with the actual answer, replacing "unconfirmed" throughout this compliance category.

## Related documents

[`36-compliance-requirements-matrix.md`](36-compliance-requirements-matrix.md), [`../09-qa/155-release-acceptance-criteria.md`](../09-qa/155-release-acceptance-criteria.md) (which lists this as a launch gate).
